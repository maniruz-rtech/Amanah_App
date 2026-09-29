package com.amanah.feature.core.realtime

import com.amanah.feature.core.realtime.RealtimeConnectionState.TerminationReason
import com.badoo.reaktive.observable.Observable
import com.badoo.reaktive.subject.behavior.BehaviorSubject
import com.badoo.reaktive.subject.publish.PublishSubject
import com.google.gson.Gson
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.time.Duration.Companion.milliseconds

/**
 * Concrete [RealtimeGateway] backed by OkHttp's [WebSocketListener].
 *
 * Lifecycle (FSM mirrors [RealtimeConnectionState]):
 *
 *   IDLE
 *     │ connect()
 *     ▼
 *   CONNECTING ──open──► AUTHENTICATING ──auth.accepted──► ONLINE
 *                                       └─auth.rejected──► TERMINATED(AUTH_REJECTED)
 *
 *   ONLINE ──onClosed/onFailure──► RECONNECTING(attempt, delay)
 *   RECONNECTING ──timer──► CONNECTING ...
 *
 *   disconnect() at any state ──► IDLE (drain queue, clear ACKs)
 *
 * Threading:
 *   - OkHttp's WebSocketListener callbacks fire on the OkHttp dispatcher thread.
 *   - All gateway state mutations are serialised through [executor] (single-thread)
 *     so the FSM has no races. Subjects are thread-safe so external subscribers
 *     can be on any thread.
 *
 * Observability:
 *   - State transitions are logged via [logger] for debug-drawer inspection.
 *   - Heartbeat ping/pong cadence is observable via the FSM's Reconnecting
 *     emissions (ping-failure → onDead → Reconnecting).
 */
class OkHttpRealtimeGateway(
    private val httpClient: OkHttpClient,
    private val wsBaseUrl: String,
    private val tokenProvider: TokenProvider,
    private val gson: Gson,
    private val reconnectStrategy: ReconnectStrategy = ReconnectStrategy(),
    private val executor: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor(),
    private val outboundQueue: OutboundQueue = InMemoryOutboundQueue(),
    private val ackRegistry: AckRegistry = AckRegistry(),
    private val eventDedup: EventDedup = EventDedup(),
    /**
     * Optional handler called when the WebSocket handshake is rejected with
     * HTTP 401. Implementations should attempt to refresh the access token
     * synchronously and return `true` to indicate "try again", `false` to
     * surrender (route the user to login).
     *
     * The gateway calls this at most once per [TerminationReason.AUTH_REJECTED]
     * transition. If it returns true the gateway re-runs `doOpen()` with the
     * (now refreshed) token from [tokenProvider]; otherwise it transitions to
     * Terminated(AUTH_REJECTED).
     */
    private val onAuthRetry: () -> Boolean = { false },
    private val logger: (String) -> Unit = {},
) : RealtimeGateway {

    private val stateSubject    = BehaviorSubject<RealtimeConnectionState>(RealtimeConnectionState.Idle)
    private val incomingSubject = PublishSubject<RealtimeEvent>()

    @Volatile private var socket: WebSocket? = null
    @Volatile private var isForeground = true
    @Volatile private var reconnectAttempt = 0
    @Volatile private var reconnectStartedAtMs = 0L
    @Volatile private var listener: AmanahListener? = null
    @Volatile private var heartbeat: HeartbeatScheduler? = null
    private val isConnectRequested = AtomicBoolean(false)
    private val connectionGeneration = AtomicInteger(0)

    // ── Public API ─────────────────────────────────────────────────────────────

    override val state: Observable<RealtimeConnectionState> = stateSubject

    override val incoming: Observable<RealtimeEvent> = incomingSubject

    override fun connect() {
        executor.execute {
            if (!isConnectRequested.compareAndSet(false, true)) {
                logger("connect() called but already requested")
                return@execute
            }
            if (stateSubject.value is RealtimeConnectionState.Online ||
                stateSubject.value is RealtimeConnectionState.Connecting ||
                stateSubject.value is RealtimeConnectionState.Authenticating
            ) {
                logger("connect() ignored — already in state ${stateSubject.value}")
                return@execute
            }
            doOpen()
        }
    }

    override fun disconnect() {
        executor.execute {
            isConnectRequested.set(false)
            connectionGeneration.incrementAndGet()      // invalidates any pending reconnect timer
            heartbeat?.stop()
            socket?.close(NORMAL_CLOSURE, "client requested")
            socket = null
            listener = null
            outboundQueue.clear()
            ackRegistry.failAll(reason = "disconnected")
            stateSubject.onNext(RealtimeConnectionState.Idle)
        }
    }

    override fun send(envelope: RealtimeEnvelope): Observable<SendOutcome> {
        val outcome = ackRegistry.register(envelope.eventId)
        executor.execute {
            val ws = socket
            val isOnline = stateSubject.value is RealtimeConnectionState.Online
            if (ws != null && isOnline) {
                val json = gson.toJson(envelope)
                if (!ws.send(json)) {
                    logger("send() returned false — buffering ${envelope.eventId}")
                    outboundQueue.enqueue(envelope)
                }
            } else {
                outboundQueue.enqueue(envelope)
                if (isConnectRequested.get() &&
                    stateSubject.value is RealtimeConnectionState.Idle) {
                    doOpen()
                }
            }
        }
        return outcome
    }

    override fun onForeground() {
        executor.execute {
            isForeground = true
            // If we were sleeping due to background, kick a reconnect.
            if (isConnectRequested.get() &&
                stateSubject.value is RealtimeConnectionState.Idle) {
                doOpen()
            }
        }
    }

    override fun onBackground() {
        executor.execute {
            isForeground = false
            // Foreground-only policy could be applied here. For an emergency
            // app we keep the socket alive in the background — explicit choice.
            // If you want to close on background, uncomment:
            // socket?.close(NORMAL_CLOSURE, "app backgrounded")
        }
    }

    // ── FSM transitions ────────────────────────────────────────────────────────

    private fun doOpen() {
        val token = tokenProvider.current()
        if (token.isNullOrBlank()) {
            logger("no token available — terminating")
            stateSubject.onNext(RealtimeConnectionState.Terminated(TerminationReason.AUTH_REJECTED))
            return
        }

        stateSubject.onNext(RealtimeConnectionState.Connecting)

        val request = Request.Builder()
            .url(wsBaseUrl)
            // Header-based auth — never a query string.
            // The backend reads this header during the handshake.
            .addHeader("Authorization", "Bearer $token")
            .addHeader("X-Amanah-Client", "android")
            .build()

        val gen = connectionGeneration.incrementAndGet()
        val l = AmanahListener(gen)
        listener = l
        socket = httpClient.newWebSocket(request, l)
    }

    private fun onOpened(generation: Int) = executor.execute {
        if (generation != connectionGeneration.get()) return@execute
        stateSubject.onNext(RealtimeConnectionState.Authenticating)
        // The Authorization header already authenticated us at the HTTP layer;
        // we still wait for an explicit auth.accepted envelope so the backend
        // can fail closed if it wants to enforce additional checks (device
        // fingerprint, JWT claim audit, etc.).
    }

    private fun onAuthAccepted(generation: Int) = executor.execute {
        if (generation != connectionGeneration.get()) return@execute
        reconnectAttempt = 0
        reconnectStartedAtMs = 0L
        authRetryAttempted = false   // any future 401 gets a fresh single-shot refresh
        stateSubject.onNext(RealtimeConnectionState.Online(sinceEpochMs = System.currentTimeMillis()))
        startHeartbeat()
        flushQueue()
    }

    private fun onAuthRejected(generation: Int, message: String) = executor.execute {
        if (generation != connectionGeneration.get()) return@execute
        logger("auth rejected: $message")
        heartbeat?.stop()
        socket?.close(POLICY_VIOLATION, "auth rejected")
        socket = null

        // Single retry attempt via the supplied refresh handler. If the handler
        // returns true the gateway re-opens with the freshly-stored token from
        // [tokenProvider]. Otherwise — terminal AUTH_REJECTED.
        if (isConnectRequested.get() && tryAuthRetry()) {
            logger("auth retry: refresh succeeded — reopening")
            doOpen()
            return@execute
        }

        stateSubject.onNext(RealtimeConnectionState.Terminated(TerminationReason.AUTH_REJECTED))
        ackRegistry.failAll("auth rejected")
    }

    @Volatile private var authRetryAttempted = false

    private fun tryAuthRetry(): Boolean {
        if (authRetryAttempted) return false   // single-shot
        authRetryAttempted = true
        return try { onAuthRetry() } catch (_: Throwable) { false }
    }

    private fun onDropped(generation: Int, reason: String) = executor.execute {
        if (generation != connectionGeneration.get()) return@execute
        heartbeat?.stop()
        socket = null
        listener = null
        if (!isConnectRequested.get()) return@execute

        reconnectAttempt += 1
        if (reconnectStartedAtMs == 0L) reconnectStartedAtMs = System.currentTimeMillis()
        val elapsedMs = System.currentTimeMillis() - reconnectStartedAtMs
        val elapsed = elapsedMs.milliseconds

        if (reconnectStrategy.shouldGiveUp(reconnectAttempt, elapsed)) {
            logger("reconnect gave up after $reconnectAttempt attempts ($reason)")
            stateSubject.onNext(RealtimeConnectionState.Terminated(TerminationReason.SERVER_FATAL))
            ackRegistry.failAll("server unreachable")
            return@execute
        }

        val delay = reconnectStrategy.delayFor(reconnectAttempt - 1)
        logger("reconnect #$reconnectAttempt in ${delay.inWholeMilliseconds}ms ($reason)")
        stateSubject.onNext(RealtimeConnectionState.Reconnecting(reconnectAttempt, delay))

        val gen = connectionGeneration.get()
        executor.schedule({
            if (gen != connectionGeneration.get()) return@schedule
            if (!isConnectRequested.get()) return@schedule
            doOpen()
        }, delay.inWholeMilliseconds, TimeUnit.MILLISECONDS)
    }

    private fun onIncomingPayload(generation: Int, payload: String) = executor.execute {
        if (generation != connectionGeneration.get()) return@execute
        val envelope = decode(payload) ?: return@execute

        // Deduplicate at-least-once deliveries.
        if (envelope.type != EventTypes.PONG && envelope.type != EventTypes.ACK) {
            if (!eventDedup.firstSeen(envelope.eventId)) {
                logger("dedup drop ${envelope.type}/${envelope.eventId}")
                return@execute
            }
        }

        val event = RealtimeEventParser.parse(envelope)

        when (event) {
            is RealtimeEvent.AuthAccepted -> onAuthAccepted(generation)
            is RealtimeEvent.AuthRejected -> onAuthRejected(generation, event.message)
            is RealtimeEvent.Pong          -> heartbeat?.recordPong()
            is RealtimeEvent.Ack           -> ackRegistry.onAck(event.eventId)
            else                            -> incomingSubject.onNext(event)
        }
    }

    private fun decode(payload: String): RealtimeEnvelope? = try {
        gson.fromJson(payload, RealtimeEnvelope::class.java)?.takeIf { it.eventId.isNotBlank() && it.type.isNotBlank() }
    } catch (_: Exception) {
        logger("malformed envelope ignored")
        null
    }

    // ── Heartbeat ──────────────────────────────────────────────────────────────

    private fun startHeartbeat() {
        heartbeat?.stop()
        val gen = connectionGeneration.get()
        heartbeat = HeartbeatScheduler(
            executor = executor,
            onPing   = {
                val ws = socket ?: return@HeartbeatScheduler
                val ping = RealtimeEnvelope(
                    type        = EventTypes.PING,
                    eventId     = UUID.randomUUID().toString(),
                    timestampMs = System.currentTimeMillis(),
                )
                if (!ws.send(gson.toJson(ping))) {
                    onDropped(gen, "ping send failed")
                }
            },
            onDead = {
                socket?.close(GOING_AWAY, "missed pong")
                onDropped(gen, "missed pong")
            },
        ).also { it.start() }
    }

    // ── Outbound queue flush ───────────────────────────────────────────────────

    private fun flushQueue() {
        val ws = socket ?: return
        val drain = outboundQueue.drainEligible()
        drain.expired.forEach { ackRegistry.onExpired(it, "ttl expired") }
        for (env in drain.live) {
            if (!ws.send(gson.toJson(env))) {
                outboundQueue.enqueue(env)
                break   // socket is misbehaving; let next reconnect retry
            }
        }
    }

    // ── OkHttp listener ────────────────────────────────────────────────────────

    private inner class AmanahListener(private val generation: Int) : WebSocketListener() {

        override fun onOpen(webSocket: WebSocket, response: Response) {
            this@OkHttpRealtimeGateway.onOpened(generation)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            this@OkHttpRealtimeGateway.onIncomingPayload(generation, text)
        }

        override fun onMessage(webSocket: WebSocket, bytes: okio.ByteString) {
            // Amanah uses JSON envelopes; binary frames are not part of the
            // protocol. Log & drop — never crash on rogue server frames.
            logger("unexpected binary frame (${bytes.size} bytes) — dropped")
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(code, reason)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            this@OkHttpRealtimeGateway.onDropped(generation, "closed: $code $reason")
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            // 401 from the upgrade request means the server rejected the token
            // during the HTTP handshake — surface it explicitly.
            if (response?.code == 401) {
                this@OkHttpRealtimeGateway.onAuthRejected(generation, "401 at handshake")
                return
            }
            // SSL/Pinning errors should fast-fail rather than reconnect-loop.
            val tlsFail = t is javax.net.ssl.SSLPeerUnverifiedException ||
                          t is javax.net.ssl.SSLHandshakeException
            if (tlsFail) {
                executor.execute {
                    if (generation != connectionGeneration.get()) return@execute
                    heartbeat?.stop()
                    socket = null
                    stateSubject.onNext(RealtimeConnectionState.Terminated(TerminationReason.TLS_FAILED))
                    ackRegistry.failAll("tls failed")
                }
                return
            }
            this@OkHttpRealtimeGateway.onDropped(generation, "failure: ${t.javaClass.simpleName}")
        }
    }

    // ── Constants ──────────────────────────────────────────────────────────────

    private companion object {
        const val NORMAL_CLOSURE   = 1000
        const val GOING_AWAY       = 1001
        const val POLICY_VIOLATION = 1008
    }
}
