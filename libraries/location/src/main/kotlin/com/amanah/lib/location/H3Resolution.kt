package com.amanah.lib.location

object H3Resolution {
    const val WORLD      = 0   // continents
    const val CONTINENT  = 2
    const val COUNTRY    = 4
    const val CITY       = 6   // ~36 km²
    const val DISTRICT   = 7   // ~5.16 km²   — default for emergency broadcast
    const val BLOCK      = 9   // ~0.105 km²  — precise proximity
    const val BUILDING   = 11  // ~450 m²

    /**
     * k-ring radius used for emergency neighbor search.
     * k=1 → 7 cells (~5-6 km radius at resolution 7), covers typical urban
     *        emergency response range without over-notifying.
     * k=2 → 19 cells, used in low-density / rural contexts.
     */
    const val EMERGENCY_K_RING = 1
    const val RURAL_K_RING     = 2
}
