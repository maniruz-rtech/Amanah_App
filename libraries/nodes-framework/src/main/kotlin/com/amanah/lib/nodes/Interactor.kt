package com.amanah.lib.nodes

import com.badoo.reaktive.disposable.CompositeDisposable
import com.badoo.reaktive.disposable.Disposable
import com.badoo.reaktive.disposable.addTo
import io.reactivex.disposables.CompositeDisposable as RxCompositeDisposable
import io.reactivex.disposables.Disposable as RxDisposable

/**
 * "Context" layer of the Node — owns all business logic and state transitions.
 *
 * Lifecycle:
 *   [onAttach] → node becomes active; start Reaktive subscriptions here.
 *   [onDetach] → node is destroyed; all subscriptions in [disposables] are auto-cleared.
 *
 * Router and View references are injected by the owning [Node] before [onAttach] fires.
 */
@Suppress("FINITE_BOUNDS_VIOLATION")
abstract class Interactor<
    ViewType : NodeView<*, *>,
    RouterType : Router<*>,
> {
    protected var view: ViewType? = null
        private set

    protected var router: RouterType? = null
        private set

    protected val disposables = CompositeDisposable()
    protected val rxDisposables = RxCompositeDisposable()

    internal fun attach(view: ViewType, router: RouterType) {
        this.view = view
        this.router = router
        onAttach()
    }

    internal fun detach() {
        onDetach()
        disposables.clear()
        rxDisposables.clear()
        view = null
        router = null
    }

    protected open fun onAttach() {}
    protected open fun onDetach() {}

    protected fun Disposable.autoDispose() = addTo(disposables)
    protected fun RxDisposable.autoDispose() = also { rxDisposables.add(it) }
}
