package com.amanah.feature.auth.node.login

import com.amanah.feature.auth.mvi.LoginFeature
import com.amanah.feature.auth.mvi.LoginNews
import com.amanah.lib.nodes.Interactor
import io.reactivex.Observable

class LoginInteractor(
    private val feature: LoginFeature = LoginFeature(),
) : Interactor<LoginView, LoginRouter>() {

    override fun onAttach() {
        // MVICore Feature is an ObservableSource<State>; wrap to Observable so
        // we get the Consumer-accepting `subscribe(Consumer<T>)` overload.
        Observable.wrap(feature).subscribe { state -> view?.render(state) }
            .autoDispose()

        Observable.wrap(feature.news).subscribe { news ->
            when (news) {
                is LoginNews.AuthenticatedAsAdmin ->
                    router?.navigateToAdmin(news.user)
                is LoginNews.AuthenticatedAsUser  ->
                    router?.navigateToUser(news.user)
                LoginNews.NavigateToForgotPassword ->
                    router?.navigateToPasswordReset()
            }
        }.autoDispose()

        view?.events = { wish -> feature.accept(wish) }
    }

    override fun onDetach() {
        view?.events = null
        feature.dispose()
    }
}
