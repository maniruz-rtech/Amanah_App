package com.amanah.feature.user.repository

import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.TrustedContactDto
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.core.repository.apiCall

class TrustedContactsRepository(
    private val api: ApiService,
) {
    suspend fun list(): Outcome<List<TrustedContactDto>> =
        apiCall { api.listTrustedContacts() }

    // NOTE: add/update/delete endpoints exist on the backend but aren't yet
    // exposed in [ApiService]. Add them when wiring the trusted-contacts
    // management screens. Doing so does not require any backend changes.
}
