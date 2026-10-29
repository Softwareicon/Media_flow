/** Mirrors backend/app/schemas.py. */
export type AnalysisStatus = 'downloadable' | 'link_only' | 'needs_connection' | 'not_configured' | 'unavailable' | 'export_only';
export type DownloadMode = 'direct' | 'connected_account' | 'operator_api' | 'link_only' | 'export_only';

export interface Alternative {
  label: string;
  description: string;
  url?: string | null;
}

export interface MediaOption {
  id: string;
  kind: 'video' | 'image' | 'audio';
  label: string;
  quality_label?: string | null;
  width?: number | null;
  height?: number | null;
  bitrate?: number | null;
  mime_type: string;
  extension: string;
  size_bytes?: number | null;
  size_is_estimate: boolean;
  has_audio?: boolean | null;
  is_original: boolean;
  note?: string | null;
}

export interface Analysis {
  analysis_id: string | null;
  source_url: string;
  platform: string;
  platform_name: string;
  status: AnalysisStatus;
  title?: string | null;
  author?: string | null;
  thumbnail_url?: string | null;
  duration_seconds?: number | null;
  media_type: 'video' | 'image' | 'audio' | 'gallery' | 'unknown';
  options: MediaOption[];
  best_option_id?: string | null;
  explanation?: string | null;
  official_url?: string | null;
  alternatives: Alternative[];
  expires_at?: string | null;
}

export interface ServerDownload {
  id: string;
  platform: string;
  source_url: string;
  title: string | null;
  option_id: string;
  quality_label: string | null;
  mime_type: string;
  file_name: string;
  expected_bytes: number | null;
  received_bytes: number | null;
  status: 'authorized' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  error_code: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface DownloadTicket {
  download: ServerDownload;
  media_url: string;
  request_headers: Record<string, string>;
  url_expires_at: string | null;
  max_bytes: number;
}

export interface PlatformInfo {
  key: string;
  name: string;
  domains: string[];
  capabilities: { official_download: boolean; api_access: boolean; user_authorized_export: boolean; direct_media_urls: boolean };
  download_mode: DownloadMode;
  configured: boolean;
  requires_connection: boolean;
  connected: boolean;
  media_types: Array<'video' | 'image' | 'audio'>;
  summary: string;
  limitations: string[];
  alternatives: Alternative[];
}

export interface SessionOut {
  token: string;
  user_id: string;
  is_anonymous: boolean;
  email: string | null;
  expires_at: string;
}

export interface Account {
  user_id: string;
  email: string | null;
  is_anonymous: boolean;
  keep_server_history: boolean;
  connections: string[];
  created_at: string;
}

export interface Connection {
  platform: string;
  configured: boolean;
  connected: boolean;
  username: string | null;
  expires_at: string | null;
}
