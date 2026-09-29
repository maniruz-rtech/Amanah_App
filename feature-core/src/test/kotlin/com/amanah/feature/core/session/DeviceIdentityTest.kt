package com.amanah.feature.core.session

import java.util.UUID
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceIdentityTest {

    private class InMemoryStore(var value: String? = null) : DeviceIdStore {
        var writes = 0
        override fun read(): String? = value
        override fun write(id: String) { value = id; writes++ }
    }

    @Test fun `generates a valid uuid once and persists it`() {
        val store = InMemoryStore()
        val id = DeviceIdentity(store).deviceUuid

        assertEquals(id, UUID.fromString(id).toString())
        assertEquals(id, store.value)
        assertEquals(1, store.writes)
    }

    @Test fun `same value on every read within a process`() {
        val store = InMemoryStore()
        val identity = DeviceIdentity(store)

        assertEquals(identity.deviceUuid, identity.deviceUuid)
        assertEquals(1, store.writes)
    }

    @Test fun `a new process reads the persisted id instead of generating another`() {
        val store = InMemoryStore()
        val first = DeviceIdentity(store).deviceUuid
        // simulate process death + restart: new DeviceIdentity over the same storage
        val second = DeviceIdentity(store, generate = { error("must not generate again") }).deviceUuid

        assertEquals(first, second)
        assertEquals(1, store.writes)
    }

    @Test fun `blank persisted value is replaced`() {
        val store = InMemoryStore("  ")
        val id = DeviceIdentity(store, generate = { "fresh-id" }).deviceUuid

        assertEquals("fresh-id", id)
        assertEquals("fresh-id", store.value)
    }

    @Test fun `different installs get different ids`() {
        val a = DeviceIdentity(InMemoryStore()).deviceUuid
        val b = DeviceIdentity(InMemoryStore()).deviceUuid
        assertNotEquals(a, b)
        assertTrue(a.isNotEmpty() && b.isNotEmpty())
    }
}
