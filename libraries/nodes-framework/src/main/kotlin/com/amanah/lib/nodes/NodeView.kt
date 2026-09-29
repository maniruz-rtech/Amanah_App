package com.amanah.lib.nodes

/**
 * Marker interface for all Compose-based node views.
 *
 * Views are intentionally thin: they hold zero business logic and only emit
 * typed [Event] objects back to their [Interactor] via the [events] callback.
 * State flows IN through [render]; user actions flow OUT through [events].
 */
interface NodeView<State : Any, Event : Any> {

    /** Callback wired by [Node.onAttach] — delivers user events to the interactor. */
    var events: ((Event) -> Unit)?

    /** Called by the interactor every time a new [State] should be reflected in UI. */
    fun render(state: State)
}
