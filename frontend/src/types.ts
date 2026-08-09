// Shared TypeScript types — single source of truth for API shapes.
// Never display graph_immutable_id or conversation_id in the UI.

export interface RecordHeader {
  id: string;
  graph_immutable_id: string;
  conversation_id: string;
  job_id?: string;
  ep_reference?: string;
  candidate_name?: string;
  tcs_eligibility: string;
  domain_status: string;
  received_at: string;
  created_at: string;
  latest_logical_timestamp?: string;
  latest_logical_author?: string;
  logical_message_count?: number;
  record_version: number;
  skill?: string;
  customer?: string;
  location?: string;
  thread_message_count?: number;
  source_content_warning?: string;
  // Interview operational fields (surfaced from payload at list time)
  feedback_due_at?: string;
  interview_state?: string;
  interview_updated_at?: string;
}

export interface TimelineEntry {
  entry_id: string;
  record_id: string;
  sender: string;
  timestamp: string;
  body_preview: string;
  classification?: string;
  is_system_note: boolean;
  to_recipients?: string[];
  cc_recipients?: string[];
  reply_to?: string;
  graph_immutable_id?: string; // internal: never display, used for Original Submission match
  conversation_id?: string;
  role?: string;
}

export interface StructuredEvidence {
  category: string;
  workflow_status: string;
  reason_code: string;
  timer_anchor_timestamp?: string;
  latest_logical_timestamp?: string;
  logical_messages_evaluated: number;
}

export interface LinkedConversation {
  conversation_id: string;
  role: string;
  subject?: string;
  received_at?: string;
  linked_at: string;
  linked_by: string;
  thread_messages?: any[];
}

export interface LinkedInterviewSuggestion {
  suggestion_id: string;
  record_id: string;
  conversation_id: string;
  candidate_name?: string;
  job_id?: string;
  ep_reference?: string;
  submission_subject?: string;
  submission_received_at?: string;
  interview_subject?: string;
  interview_received_at?: string;
  latest_interview_message_excerpt?: string;
  latest_interview_message_sender?: string;
  thread_messages?: any[];
}

export interface FullRecord {
  id: string;
  graph_immutable_id: string;
  conversation_id: string;
  job_id?: string;
  ep_reference?: string;
  candidate_name?: string;
  skill?: string;
  customer?: string;
  location?: string;
  domain_status: string;
  received_at: string;
  created_at: string;
  interview_state?: string;
  interview_updated_at?: string;
  feedback_due_at?: string;
  manager_notes: string;
  system_notes: string;
  close_reason?: string;
  close_note?: string;
  closed_at?: string;
  latest_update?: string;
  latest_sender?: string;
  latest_logical_timestamp?: string;
  latest_logical_author?: string;
  logical_message_count?: number;
  record_version: number;
  structured_evidence?: StructuredEvidence;
  is_operational_record_only?: boolean;
  thread_message_count?: number;
  thread_messages?: any[];
  retention_expired?: boolean;
  expires_at?: string;
  timeline: TimelineEntry[];
  linked_conversations?: LinkedConversation[];
  interview_suggestions?: LinkedInterviewSuggestion[];
  attachment_count: number;
  source_content_warning?: string;
}

export interface DashboardSummary {
  awaiting_response: number;
  pending_follow_up: number;
  interview_awaiting_confirmation: number;
  interview_request_scheduled: number;
  awaiting_feedback: number;
  feedback_due: number;
  manager_action_required: number;
  in_evaluation: number;
  needs_review: number;
  incomplete: number;
  complete_records: number;
  closed: number;
  total: number;
  auth_status: string;
  records: RecordHeader[];
}

export type ViewName = 'dashboard' | 'records' | 'interviews' | 'retention';

export interface ConfigStatus {
  graph_enabled: boolean;
  drafts_enabled: boolean;
  draft_creation_available: boolean;
  mail_send_prohibited: boolean;
}

export interface DraftRecipientPreview {
  record_id: string;
  conversation_id: string;
  source_message_id: string;
  source_message_sender: string;
  to: string[];
  cc: string[];
  bcc: string[];
  reply_to: string;
  default_text: string;
}

export interface DraftApprovalRequest {
  record_id: string;
  content: string;
  to: string[];
  cc: string[];
  bcc: string[];
  conversation_id: string;
  source_message_id: string;
}

export interface DraftApprovalResponse {
  is_approved: boolean;
  approval_hash: string;
  idempotency_key: string;
  approved_at: string;
  canonical_summary: string;
}

export type DraftOperationState = 'APPROVED' | 'CREATING' | 'RECOVERED_PENDING_FINALIZATION' | 'CREATED' | 'FAILED_RECONCILABLE' | 'SUPERSEDED';

export interface DraftOperationStatus {
  idempotency_key: string;
  record_id: string;
  approval_hash: string;
  state: DraftOperationState;
  can_create: boolean;
  can_reconcile: boolean;
  can_resume: boolean;
  can_reset: boolean;
  verified: boolean;
  message: string;
}

export interface DraftCreationResult {
  draft_id: string;
  record_id: string;
  verified: boolean;
  operation_state: string;
  is_synthetic: boolean;
  message: string;
}

export interface DraftCreateRequest {
  record_id: string;
  content: string;
  to: string[];
  cc: string[];
  bcc: string[];
  approval_hash: string;
  idempotency_key: string;
  conversation_id: string;
  source_message_id: string;
}
