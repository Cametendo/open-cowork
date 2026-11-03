export type Role = "admin" | "user" | "pending";

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  created_at: number;
  last_active_at: number;
  github_login?: string | null;
  settings?: UserSettings;
}

export interface UserSettings {
  theme?: "system" | "dark" | "light";
  system_prompt?: string;
  default_model?: string;
  cowork_default_model?: string;
  cowork_instructions?: string;
  cowork_approval_mode?: "ask" | "auto";
}

export interface PublicConfig {
  name: string;
  version: string;
  onboarding: boolean;
  features: { enable_signup: boolean; cowork: boolean; github: boolean };
}

export interface AdminConfig {
  webui_name: string;
  enable_signup: boolean;
  default_user_role: "user" | "pending";
  enable_title_generation: boolean;
  cowork_enabled: boolean;
  cowork_allow_shell: boolean;
  cowork_command_timeout: number;
  cowork_max_steps: number;
  cowork_ollama_num_ctx: number;
  github_enabled: boolean;
}

export interface Model {
  id: string;
  name: string;
  provider: "ollama" | "openai";
  connection_id: string;
  connection_name: string;
  details: Record<string, unknown>;
}

export interface Connection {
  id: string;
  type: "ollama" | "openai";
  name: string;
  base_url: string;
  has_api_key: boolean;
  enabled: boolean;
  prefix_id: string | null;
  model_ids: string[];
  created_at: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string;
  reasoning?: string;
  images?: string[];
  error?: string;
  stopped?: boolean;
  usage?: Record<string, number | null>;
  created_at: number;
}

export interface ChatSummary {
  id: string;
  title: string;
  model: string | null;
  pinned: boolean;
  created_at: number;
  updated_at: number;
}

export interface ChatParams {
  system?: string;
  temperature?: number | null;
  max_tokens?: number | null;
  num_ctx?: number | null;
}

export interface Chat extends ChatSummary {
  messages: ChatMessage[];
  params: ChatParams;
}

// ---------------------------------------------------------------- Cowork

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface CoworkMessage {
  id: string;
  role: "user" | "assistant" | "tool" | "event";
  content: string;
  model?: string;
  reasoning?: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
  is_error?: boolean;
  meta?: Record<string, any>;
  notice?: boolean;
  stopped?: boolean;
  created_at: number;
}

export interface PlanItem {
  title: string;
  status: "pending" | "in_progress" | "completed";
}

export interface CoworkSummary {
  id: string;
  title: string;
  model: string | null;
  status: "idle" | "running" | "error";
  workspace_type: "scratch" | "repo";
  workspace_path: string;
  repo_id: string | null;
  repo_name: string | null;
  branch: string | null;
  base_branch: string | null;
  approval_mode: "ask" | "auto";
  created_at: number;
  updated_at: number;
}

export interface CoworkSession extends CoworkSummary {
  messages: CoworkMessage[];
  plan: PlanItem[];
  last_error: string | null;
  run: { id: string; done: boolean } | null;
}

export interface FileEntry {
  name: string;
  path: string;
  type: "dir" | "file";
  size: number | null;
  modified: number;
  ignored: boolean;
}

// ---------------------------------------------------------------- GitHub

export interface GitHubStatus {
  connected: boolean;
  login: string | null;
  name: string | null;
  avatar_url: string | null;
  html_url: string | null;
  scopes: string | null;
  repo_dir: string;
}

export interface RemoteRepo {
  full_name: string;
  name: string;
  owner: string;
  description: string | null;
  private: boolean;
  default_branch: string;
  html_url: string;
  pushed_at: string | null;
  language: string | null;
  stargazers_count: number;
  local_id: string | null;
}

export interface LocalRepo {
  id: string;
  full_name: string;
  path: string;
  default_branch: string;
  html_url: string | null;
  private: boolean;
  source: "github" | "local";
  user_id: string;
  created_at: number;
  last_pulled_at: number | null;
  exists?: boolean;
  current_branch?: string | null;
  busy?: boolean;
}

export interface GitFile {
  path: string;
  status: string;
  staged: boolean;
  orig_path: string | null;
  added?: number;
  removed?: number;
  diff?: string;
  binary?: boolean;
  truncated?: boolean;
  note?: string;
}

export interface GitStatus {
  branch: string | null;
  upstream: string | null;
  ahead: number;
  behind: number;
  files: GitFile[];
  clean: boolean;
  busy?: boolean;
}

export interface PullRequest {
  number: number;
  title: string;
  html_url: string;
  state: string;
  draft: boolean;
  head: string;
  base: string;
}
