/**
 * Playback position persistence store.
 * Part of feature: 004-video-segment-aggregation
 *
 * Persists playback position to localStorage for resume functionality.
 */

// Storage key prefix
const STORAGE_PREFIX = 'vod_position_'

// Expiry time in milliseconds (30 days)
const EXPIRY_MS = 30 * 24 * 60 * 60 * 1000

// Throttle interval for saving position (5 seconds)
const THROTTLE_MS = 5000

export interface PlaybackState {
  position: number       // Unified position in seconds
  segmentId: number      // Current segment ID
  timestamp: number      // When this was saved (Unix timestamp)
}

/**
 * Generate storage key for a session.
 * Format: vod_position_{anchorName}_{sessionTimestamp}
 */
export function getStorageKey(anchorName: string, sessionTimestamp: string): string {
  // Sanitize the anchor name to avoid issues with special characters
  const sanitizedAnchor = anchorName.replace(/[/\\]/g, '_')
  return `${STORAGE_PREFIX}${sanitizedAnchor}_${sessionTimestamp}`
}

/**
 * Save playback position to localStorage.
 * Position is only saved if it differs significantly from the last saved position.
 */
export function savePosition(
  anchorName: string,
  sessionTimestamp: string,
  position: number,
  segmentId: number
): void {
  try {
    const key = getStorageKey(anchorName, sessionTimestamp)
    const state: PlaybackState = {
      position,
      segmentId,
      timestamp: Date.now(),
    }
    localStorage.setItem(key, JSON.stringify(state))
  } catch (e) {
    // localStorage might be full or unavailable (private browsing)
    console.warn('Failed to save playback position:', e)
  }
}

/**
 * Load playback position from localStorage.
 * Returns null if no position is saved, position is expired, or invalid.
 */
export function loadPosition(
  anchorName: string,
  sessionTimestamp: string,
  maxDuration?: number
): PlaybackState | null {
  try {
    const key = getStorageKey(anchorName, sessionTimestamp)
    const stored = localStorage.getItem(key)

    if (!stored) {
      return null
    }

    const state: PlaybackState = JSON.parse(stored)

    // Check expiry
    if (Date.now() - state.timestamp > EXPIRY_MS) {
      // Position has expired, remove it
      localStorage.removeItem(key)
      return null
    }

    // Validate position if maxDuration is provided
    if (maxDuration !== undefined && state.position > maxDuration) {
      // Position exceeds available duration, reset
      localStorage.removeItem(key)
      return null
    }

    return state
  } catch (e) {
    console.warn('Failed to load playback position:', e)
    return null
  }
}

/**
 * Clear saved position for a session.
 * Call this when playback completes.
 */
export function clearPosition(anchorName: string, sessionTimestamp: string): void {
  try {
    const key = getStorageKey(anchorName, sessionTimestamp)
    localStorage.removeItem(key)
  } catch (e) {
    console.warn('Failed to clear playback position:', e)
  }
}

/**
 * Create a throttled position saver.
 * Returns a function that saves position but throttles calls to every THROTTLE_MS.
 */
export function createThrottledSaver(
  anchorName: string,
  sessionTimestamp: string
): (position: number, segmentId: number) => void {
  let lastSaveTime = 0
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  return (position: number, segmentId: number) => {
    const now = Date.now()

    // If enough time has passed, save immediately
    if (now - lastSaveTime >= THROTTLE_MS) {
      savePosition(anchorName, sessionTimestamp, position, segmentId)
      lastSaveTime = now

      // Clear any pending timeout
      if (timeoutId) {
        clearTimeout(timeoutId)
        timeoutId = null
      }
    } else {
      // Schedule a save for later if not already scheduled
      if (!timeoutId) {
        const delay = THROTTLE_MS - (now - lastSaveTime)
        timeoutId = setTimeout(() => {
          savePosition(anchorName, sessionTimestamp, position, segmentId)
          lastSaveTime = Date.now()
          timeoutId = null
        }, delay)
      }
    }
  }
}

/**
 * Clean up expired positions from localStorage.
 * Call this occasionally to free up storage space.
 */
export function cleanupExpiredPositions(): void {
  try {
    const keysToRemove: string[] = []
    const now = Date.now()

    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && key.startsWith(STORAGE_PREFIX)) {
        try {
          const stored = localStorage.getItem(key)
          if (stored) {
            const state: PlaybackState = JSON.parse(stored)
            if (now - state.timestamp > EXPIRY_MS) {
              keysToRemove.push(key)
            }
          }
        } catch {
          // Invalid data, remove it
          keysToRemove.push(key)
        }
      }
    }

    keysToRemove.forEach(key => localStorage.removeItem(key))
  } catch (e) {
    console.warn('Failed to cleanup expired positions:', e)
  }
}
