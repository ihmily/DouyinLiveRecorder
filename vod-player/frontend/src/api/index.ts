/**
 * API client for VOD Player backend.
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

// Types
export interface Platform {
  name: string
  anchor_count: number
  session_count: number
}

export interface Anchor {
  name: string
  session_count: number
  last_live: string | null
}

export interface SessionSummary {
  id: number
  started_at: string
  ended_at: string | null
  duration: number | null
  segment_count: number
  total_size: number | null
}

export interface SessionListResponse {
  total: number
  page: number
  limit: number
  items: SessionSummary[]
}

export interface SegmentInfo {
  id: number
  index: number
  duration: number | null
  size: number | null
  mp4_status: 'pending' | 'processing' | 'completed' | 'failed'
}

export interface SessionDetail {
  id: number
  platform: string
  anchor_name: string
  live_title: string | null
  started_at: string
  ended_at: string | null
  total_duration: number | null
  segments: SegmentInfo[]
}

export interface PlaybackUrl {
  url: string
  expires_at: string
  duration: number | null
  title: string
}

// API functions
export async function getPlatforms(): Promise<Platform[]> {
  const response = await api.get<Platform[]>('/platforms')
  return response.data
}

export async function getAnchors(platform: string): Promise<Anchor[]> {
  const response = await api.get<Anchor[]>(`/platforms/${encodeURIComponent(platform)}/anchors`)
  return response.data
}

export async function getSessions(
  anchorName: string,
  options?: { platform?: string; page?: number; limit?: number }
): Promise<SessionListResponse> {
  const params = new URLSearchParams()
  if (options?.platform) params.set('platform', options.platform)
  if (options?.page) params.set('page', String(options.page))
  if (options?.limit) params.set('limit', String(options.limit))

  const response = await api.get<SessionListResponse>(
    `/anchors/${encodeURIComponent(anchorName)}/sessions?${params.toString()}`
  )
  return response.data
}

export async function getSession(sessionId: number): Promise<SessionDetail> {
  const response = await api.get<SessionDetail>(`/sessions/${sessionId}`)
  return response.data
}

export async function getPlayUrl(segmentId: number): Promise<PlaybackUrl> {
  const response = await api.get<PlaybackUrl>(`/segments/${segmentId}/play`)
  return response.data
}

export default api
