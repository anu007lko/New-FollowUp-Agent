import { useEffect, useRef, useState } from 'react';
import type { FullRecord, LinkedInterviewSuggestion, LinkedConversation, DraftRecipientPreview, DraftApprovalResponse, DraftCreationResult, DraftOperationStatus } from '../types';
import { formatTimestamp, getDisplayLabel } from '../utils/displayStatus';
import { CustomDropdown } from './CustomDropdown';
import { playSound } from '../utils/audio';

interface ManagerActionModalsProps {
  activeModal: string | null;
  record: FullRecord;
  selectedSuggestion?: LinkedInterviewSuggestion | null;
  selectedLinked?: LinkedConversation | null;
  onCloseModal: () => void;
  onSuccessAction: (endpoint?: string, payloadData?: any) => void;
  onRefreshRecord?: () => Promise<FullRecord | void>;
}

export function ManagerActionModals({
  activeModal,
  record,
  selectedSuggestion,
  selectedLinked,
  onCloseModal,
  onSuccessAction,
  onRefreshRecord,
}: ManagerActionModalsProps) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Form states
  const [noteText, setNoteText] = useState('');
  const [interviewChoice, setInterviewChoice] = useState('completed');
  const [rescheduleDate, setRescheduleDate] = useState('');
  const [rescheduleTime, setRescheduleTime] = useState('');
  const [rescheduleTz, setRescheduleTz] = useState('America/New_York');
  const [outcomeCategory, setOutcomeCategory] = useState('Position Closed');
  const [outcomeNotes, setOutcomeNotes] = useState('');
  const [closeReason, setCloseReason] = useState('Position closed');
  const [closeNote, setCloseNote] = useState('');
  const [reopenReason, setReopenReason] = useState('');

  // Status Action Confirmation State
  const [actionReason, setActionReason] = useState('');
  const [actionNote, setActionNote] = useState('');

  // Draft Wizard states
  const [draftWizardStep, setDraftWizardStep] = useState<'decision' | 'review' | 'recovery' | 'created'>('decision');
  const [draftPreview, setDraftPreview] = useState<DraftRecipientPreview | null>(null);
  const [draftContent, setDraftContent] = useState('');
  const [draftBccText, setDraftBccText] = useState('');
  const [draftApproval, setDraftApproval] = useState<DraftApprovalResponse | null>(null);
  const [draftStatus, setDraftStatus] = useState<DraftOperationStatus | null>(null);
  const [csrfToken, setCsrfToken] = useState('');
  const [currentVersion, setCurrentVersion] = useState(record.record_version);
  const inFlight = useRef(false);

  useEffect(() => {
    setCurrentVersion(record.record_version);
  }, [record.record_version]);

  useEffect(() => {
    setDraftWizardStep('decision'); setDraftPreview(null); setDraftApproval(null); setDraftStatus(null);
    setDraftContent(''); setDraftBccText(''); setErrorMessage(null); setCurrentVersion(record.record_version);
    setActionReason(''); setActionNote('');
    if (activeModal) {
      fetch('/api/v1/session/csrf-token', { method: 'POST' })
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(d => setCsrfToken(d.csrf_token || ''))
        .catch(() => setErrorMessage('Secure local session could not be established.'));
      if (activeModal === 'interview') {
        const dDate = record.interview_date || record.structured_evidence?.interview_date || '';
        const dTime = record.interview_time || record.structured_evidence?.interview_time || '';
        const dTz = record.interview_timezone || record.structured_evidence?.timezone || 'America/New_York';
        setRescheduleDate(dDate);
        setRescheduleTime(dTime);
        setRescheduleTz(dTz);
        const istate = (record.interview_state || '').toLowerCase();
        if (['scheduled', 'completed', 'rescheduled', 'cancelled', 'not_confirmed'].includes(istate)) {
          setInterviewChoice(istate);
        } else if (record.domain_status === 'InterviewAwaitingConfirmation' || record.domain_status === 'InterviewRequestScheduled' || record.domain_status === 'InterviewScheduled') {
          setInterviewChoice('scheduled');
        } else {
          setInterviewChoice('completed');
        }
      }
      if (activeModal === 'followup') {
        fetch(`/api/v1/records/${record.id}/draft-status`)
          .then(async r => r.ok ? r.json() : null)
          .then((status: DraftOperationStatus | null) => {
            if (!status || !['CREATING', 'FAILED_RECONCILABLE', 'RECOVERED_PENDING_FINALIZATION'].includes(status.state)) return;
            setDraftStatus(status);
            setDraftApproval({
              is_approved: true,
              approval_hash: status.approval_hash,
              idempotency_key: status.idempotency_key,
              approved_at: '',
              canonical_summary: status.message,
            });
            setDraftWizardStep('recovery');
          })
          .catch(() => undefined);
      }
    }
  }, [activeModal, record.id]);
  if (!activeModal) return null;

  const basePayload = {
    record_id: record.id,
    graph_immutable_id: record.graph_immutable_id,
    conversation_id: record.conversation_id,
    record_version: currentVersion,
  };

  function mapCategoryToOutcomeOptionId(cat: string): string {
    const c = (cat || '').trim().toLowerCase();
    if (c.includes('position closed')) return 'POSITION_CLOSED';
    if (c.includes('client rejected') || c.includes('rejection')) return 'CLIENT_REJECTED';
    if (c.includes('withdrawn')) return 'CANDIDATE_WITHDRAWN';
    if (c.includes('duplicate')) return 'DUPLICATE_SUBMISSION';
    if (c.includes('placed') || c.includes('joined')) return 'PLACED_JOINED';
    if (c.includes('unavailable') || c.includes('no longer')) return 'NO_LONGER_AVAILABLE';
    if (c.includes('no follow')) return 'NO_FOLLOW_UP_NEEDED';
    if (c.includes('hold')) return 'ON_HOLD';
    if (c.includes('review') || c.includes('keep')) return 'KEEP_IN_REVIEW';
    return 'OTHER_CLOSED';
  }

  const handleApiSubmit = async (endpoint: string, payloadData: any = {}) => {
    if (endpoint === 'outcome-decision' || endpoint === 'review_outcome' || endpoint === 'set_outcome') {
      playSound('apply');
    } else if (endpoint === 'close' || endpoint.startsWith('action_')) {
      playSound('close');
    }
    setSubmitting(true);
    setErrorMessage(null);
    try {
      let token = csrfToken;
      if (!token) {
        const tokenRes = await fetch('/api/v1/session/csrf-token', { method: 'POST' }).catch(() => null);
        if (tokenRes && tokenRes.ok) {
          const tokenData = await tokenRes.json().catch(() => ({}));
          token = tokenData.csrf_token || '';
          setCsrfToken(token);
        }
      }

      let actionEndpoint = `/api/v1/records/${record.id}/action`;
      let actionPayload: any = null;

      if (endpoint === 'close' || endpoint === 'action_closed' || endpoint === 'action_rejected' || endpoint === 'action_withdrawn' || endpoint === 'action_placed' || endpoint === 'action_unavailable') {
        actionPayload = {
          action_id: 'CLOSE_RECORD',
          record_version: currentVersion,
          reason: payloadData?.reason || closeReason,
          note: payloadData?.close_note || closeNote || undefined
        };
      } else if (endpoint === 'action_duplicate') {
        actionPayload = {
          action_id: 'MARK_DUPLICATE_SUBMISSION',
          record_version: currentVersion,
          note: payloadData?.close_note || closeNote || undefined
        };
      } else if (endpoint === 'reopen') {
        actionPayload = {
          action_id: 'REOPEN_RECORD',
          record_version: currentVersion,
          note: payloadData?.reason || reopenReason || undefined
        };
      } else if (endpoint === 'note') {
        actionPayload = {
          action_id: 'ADD_NOTE',
          record_version: currentVersion,
          note: payloadData?.note_text || noteText
        };
      } else if (endpoint === 'outcome-decision' || endpoint === 'review_outcome' || endpoint === 'set_outcome') {
        actionPayload = {
          action_id: 'REVIEW_OUTCOME',
          record_version: currentVersion,
          outcome_option_id: payloadData?.outcome_option_id || mapCategoryToOutcomeOptionId(outcomeCategory),
          note: outcomeNotes || undefined
        };
      } else {
        actionEndpoint = `/api/v1/records/${record.id}/${endpoint}`;
        actionPayload = { ...basePayload, ...payloadData };
      }

      const res = await fetch(actionEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-csrf-token': token,
        },
        body: JSON.stringify(actionPayload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Action failed' }));
        if (res.status === 409) {
          if (onRefreshRecord) await onRefreshRecord();
          throw new Error('The record was updated by another process. Version refreshed. Please review and submit again if still applicable.');
        }
        throw new Error(err.detail || 'Action failed');
      }

      onSuccessAction(endpoint, payloadData);
      onCloseModal();
    } catch (e: any) {
      setErrorMessage(e.message || 'Action failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleFollowUpDecision = async () => {
    if (inFlight.current) return; inFlight.current = true;
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const decisionRes = await fetch(`/api/v1/records/${record.id}/follow-up-decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': csrfToken },
        body: JSON.stringify({ ...basePayload, decision: 'Request Follow-up' }),
      });
      if (!decisionRes.ok) {
        if (decisionRes.status === 409 && onRefreshRecord) await onRefreshRecord();
        throw new Error('Failed to record follow-up decision');
      }

      if (onRefreshRecord) {
        const refreshed = await onRefreshRecord();
        if (refreshed) setCurrentVersion(refreshed.record_version);
      }
      
      const previewRes = await fetch(`/api/v1/records/${record.id}/draft-preview`);
      if (!previewRes.ok) throw new Error('Failed to fetch draft preview');
      
      const preview: DraftRecipientPreview = await previewRes.json();
      setDraftPreview(preview);
      if (!draftContent) setDraftContent(preview.default_text || '');
      setDraftWizardStep('review');
    } catch (e: any) {
      setErrorMessage(e.message || 'Action failed');
    } finally {
      setSubmitting(false);
      inFlight.current = false;
    }
  };

  const handleApproveDraft = async () => {
    if (!draftPreview) return;
    const bccList = draftBccText.split(',').map(s => s.trim()).filter(Boolean);
    if (bccList.some(email => !email.endsWith('@clifyx.com'))) {
      setErrorMessage('BCC addresses must end in @clifyx.com');
      return;
    }
    if (inFlight.current) return; inFlight.current = true; setSubmitting(true);
    setErrorMessage(null);
    try {
      const approvePayload = {
        record_id: record.id,
        content: draftContent,
        to: draftPreview.to,
        cc: draftPreview.cc,
        bcc: bccList,
        conversation_id: draftPreview.conversation_id,
        source_message_id: draftPreview.source_message_id,
        record_version: currentVersion
      };
      const res = await fetch(`/api/v1/records/${record.id}/draft-approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': csrfToken },
        body: JSON.stringify(approvePayload),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        if (res.status === 409 && onRefreshRecord) {
          const refreshed = await onRefreshRecord(); if (refreshed) setCurrentVersion(refreshed.record_version);
        }
        throw new Error(
          res.status === 409
            ? 'Record updated by another process. Please review and approve again.'
            : (errorData.detail || 'Draft approval failed. Outlook draft creation may be paused.')
        );
      }
      const responseData: DraftApprovalResponse = await res.json();
      setDraftApproval(responseData);
      setDraftStatus({ idempotency_key: responseData.idempotency_key, record_id: record.id, approval_hash: responseData.approval_hash, state: 'APPROVED', can_create: true, can_reconcile: false, can_resume: false, can_reset: false, verified: false, message: 'Approved and ready to create.' });
    } catch (e: any) {
      setErrorMessage(e.message || 'Approval failed');
    } finally {
      setSubmitting(false);
      inFlight.current = false;
    }
  };

  const handleCreateDraft = async () => {
    if (!draftPreview || !draftApproval) return;
    if (inFlight.current) return; inFlight.current = true; setSubmitting(true);
    setErrorMessage(null);
    try {
      const bccList = draftBccText.split(',').map(s => s.trim()).filter(Boolean);
      const createPayload = {
        record_id: record.id,
        content: draftContent,
        to: draftPreview.to,
        cc: draftPreview.cc,
        bcc: bccList,
        approval_hash: draftApproval.approval_hash,
        idempotency_key: draftApproval.idempotency_key,
        conversation_id: draftPreview.conversation_id,
        source_message_id: draftPreview.source_message_id,
        record_version: currentVersion
      };
      const res = await fetch(`/api/v1/records/${record.id}/draft-create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': csrfToken },
        body: JSON.stringify(createPayload),
      });
      if (!res.ok) {
        if (res.status === 409 && onRefreshRecord) {
          const refreshed = await onRefreshRecord(); if (refreshed) setCurrentVersion(refreshed.record_version);
        }
        const statusRes = await fetch(`/api/v1/records/${record.id}/draft-status/${draftApproval.idempotency_key}`);
        if (statusRes.ok) {
          const status: DraftOperationStatus = await statusRes.json();
          if (['CREATING', 'FAILED_RECONCILABLE', 'RECOVERED_PENDING_FINALIZATION'].includes(status.state)) {
            setDraftStatus(status);
            setDraftWizardStep('recovery');
            setErrorMessage(null);
            return;
          }
        }
        let errDetail = 'Draft creation failed';
        try {
          const errData = await res.json();
          if (errData.detail) errDetail = errData.detail;
        } catch (e) {
          // ignore parsing error
        }
        throw new Error(errDetail);
      }
      const created: DraftCreationResult = await res.json();
      if (!created.verified || created.operation_state !== 'CREATED' || created.is_synthetic || !created.draft_id) {
        throw new Error('Outlook did not return a verified live draft. Success was not recorded.');
      }
      setDraftWizardStep('created');
      onSuccessAction();
    } catch (e: any) {
      setErrorMessage(e.message || 'Draft creation failed');
    } finally {
      setSubmitting(false);
      inFlight.current = false;
    }
  };

  const handleRecoveryAction = async (action: 'reconcile' | 'resume' | 'reset') => {
    if (!draftApproval || inFlight.current) return; inFlight.current = true; setSubmitting(true); setErrorMessage(null);
    try {
      const res = await fetch(`/api/v1/records/${record.id}/draft-${action}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'x-csrf-token': csrfToken },
        body: JSON.stringify({ record_id: record.id, idempotency_key: draftApproval.idempotency_key, approval_hash: draftApproval.approval_hash, record_version: currentVersion }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 409 && onRefreshRecord) {
          const refreshed = await onRefreshRecord();
          if (refreshed) setCurrentVersion(refreshed.record_version);
          throw new Error('This record changed elsewhere. The latest state has been loaded; please review and try again.');
        }
        throw new Error(data.detail || 'Recovery action failed');
      }
      if (action === 'resume') {
        const created = data as DraftCreationResult;
        if (!created.verified || created.operation_state !== 'CREATED' || created.is_synthetic) throw new Error('Recovered draft was not verified.');
        setDraftWizardStep('created'); onSuccessAction();
      } else {
        setDraftStatus(data as DraftOperationStatus);
        if ((data as DraftOperationStatus).state === 'SUPERSEDED') { setDraftApproval(null); setDraftWizardStep('review'); }
      }
    } catch (e: any) { setErrorMessage(e.message || 'Recovery action failed'); }
    finally { setSubmitting(false); inFlight.current = false; }
  };

  return (
    <div className="modal-backdrop" onClick={() => { if (!submitting) onCloseModal(); }} role="dialog" aria-modal="true" aria-labelledby="manager-action-title" data-layer="Manager Action / Overlay">
      <div className="modal-card" onClick={e => e.stopPropagation()} data-layer="Manager Action / Dialog">
        {errorMessage && (
          <div className="modal-error" role="alert">
            {errorMessage}
          </div>
        )}

        {/* Modal: Add Note */}
        {activeModal === 'note' && (
          <div>
            <h3 className="modal-title">Add Local Manager Note</h3>
            <p className="modal-subtitle">Notes are visible locally and do not alter follow-up or retention timers.</p>
            <textarea
              className="modal-textarea"
              placeholder="Type your manager note..."
              value={noteText}
              onChange={e => setNoteText(e.target.value)}
              rows={4}
            />
            <div className="modal-actions">
              <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
              <button
                className="btn-primary"
                disabled={submitting || !noteText.trim()}
                onClick={() => handleApiSubmit('notes', { note_text: noteText })}
              >
                {submitting ? 'Saving...' : 'Save Note'}
              </button>
            </div>
          </div>
        )}

        {/* Modal: Follow-up Decision Wizard */}
        {activeModal === 'followup' && (
          <div>
            {draftWizardStep === 'decision' && (
              <>
                <div className="draft-steps" aria-label="Draft progress">
                  <span className="draft-step draft-step-active">1. Decision</span>
                  <span className="draft-step">2. Review</span>
                  <span className="draft-step">3. Create</span>
                </div>
                <h3 className="modal-title" id="manager-action-title">Prepare Follow-up Draft</h3>
                <p className="modal-subtitle">
                  Confirm the follow-up decision, then review every recipient and the complete message before creating an Outlook draft.
                </p>
                <div className="draft-safety-note" role="note">
                  <strong>Draft only.</strong> This app cannot send email. You will review and send it manually in Outlook.
                </div>
                <div className="modal-actions">
                  <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
                  <button
                    className="btn-primary"
                    disabled={submitting}
                    onClick={handleFollowUpDecision}
                  >
                    {submitting ? 'Recording...' : 'Confirm & Review Draft'}
                  </button>
                </div>
              </>
            )}

            {draftWizardStep === 'review' && draftPreview && !draftApproval && (
              <>
                <div className="draft-steps" aria-label="Draft progress">
                  <span className="draft-step draft-step-complete">✓ Decision</span>
                  <span className="draft-step draft-step-active">2. Review</span>
                  <span className="draft-step">3. Create</span>
                </div>
                <h3 className="modal-title" id="manager-action-title">Review Draft and Recipients</h3>
                <p className="modal-subtitle">Reply All recipients come from the exact Outlook message selected as the reply anchor.</p>
                <div className="draft-recipient-panel">
                  <div className="draft-recipient-row">
                    <span className="draft-recipient-label">To</span>
                    <div className="draft-recipient-chips">{draftPreview.to.map(address => <span className="draft-recipient-chip" key={`to-${address}`}>{address}</span>)}</div>
                  </div>
                  {draftPreview.cc.length > 0 && <div className="draft-recipient-row">
                    <span className="draft-recipient-label">CC</span>
                    <div className="draft-recipient-chips">{draftPreview.cc.map(address => <span className="draft-recipient-chip" key={`cc-${address}`}>{address}</span>)}</div>
                  </div>}
                </div>
                <div className="modal-form-group">
                  <label className="modal-label" htmlFor="draft-bcc">BCC <span className="modal-label-optional">Optional · @clifyx.com only</span></label>
                  <input
                    id="draft-bcc"
                    type="text"
                    className="modal-input"
                    placeholder="e.g. manager@clifyx.com"
                    value={draftBccText}
                    onChange={e => setDraftBccText(e.target.value)}
                  />
                </div>
                <div className="modal-form-group">
                  <label className="modal-label" htmlFor="draft-body">Message</label>
                  <textarea
                    id="draft-body"
                    className="modal-textarea"
                    rows={8}
                    value={draftContent}
                    onChange={e => setDraftContent(e.target.value)}
                  />
                </div>
                <div className="modal-actions">
                  <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
                  <button
                    className="btn-primary"
                    disabled={submitting || !draftContent.trim()}
                    onClick={handleApproveDraft}
                  >
                    {submitting ? 'Approving...' : 'Approve Draft & Recipients'}
                  </button>
                </div>
              </>
            )}

            {draftWizardStep === 'review' && draftPreview && draftApproval && (
              <>
                <div className="draft-steps" aria-label="Draft progress">
                  <span className="draft-step draft-step-complete">✓ Decision</span>
                  <span className="draft-step draft-step-complete">✓ Review</span>
                  <span className="draft-step draft-step-active">3. Create</span>
                </div>
                <h3 className="modal-title" id="manager-action-title">Ready to Create in Outlook</h3>
                <p className="modal-subtitle">Recipients and message are locked to this approval. Creating the draft will not send it.</p>
                <div className="modal-actions">
                  <button className="btn-secondary" onClick={() => setDraftApproval(null)} disabled={submitting}>Back to Edit</button>
                  <button
                    className="btn-primary"
                    disabled={submitting}
                    onClick={handleCreateDraft}
                  >
                    {submitting ? 'Creating...' : 'Create Draft in Outlook'}
                  </button>
                </div>
              </>
            )}

            {draftWizardStep === 'recovery' && draftStatus && (
              <>
                <h3 className="modal-title">Draft Recovery</h3>
                <p className="modal-subtitle">{draftStatus.message}</p>
                <p className="modal-subtitle">The app will never repeat draft creation while the Outlook result is uncertain.</p>
                <div className="modal-actions">
                  <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Close</button>
                  {draftStatus.can_reconcile && <button className="btn-primary" onClick={() => handleRecoveryAction('reconcile')} disabled={submitting}>Reconcile Outlook Drafts</button>}
                  {draftStatus.can_resume && <button className="btn-primary" onClick={() => handleRecoveryAction('resume')} disabled={submitting}>Resume Finalization</button>}
                  {draftStatus.can_reset && <button className="btn-secondary" onClick={() => handleRecoveryAction('reset')} disabled={submitting}>Reset After Zero-Match Check</button>}
                </div>
              </>
            )}

            {draftWizardStep === 'created' && (
              <>
                <h3 className="modal-title modal-title-success" id="manager-action-title">Draft Created</h3>
                <p className="modal-subtitle">The Reply All draft is saved in Outlook with its original conversation history. Nothing was sent.</p>
                <div className="draft-safety-note" role="status">Open Outlook to review the complete chain and send manually when ready.</div>
                <div className="modal-actions">
                  <button className="btn-primary" onClick={onCloseModal}>Close</button>
                </div>
              </>
            )}
          </div>
        )}

        {/* Modal: Confirm Interview */}
        {activeModal === 'interview' && (() => {
          const origDate = record.interview_date || record.structured_evidence?.interview_date || '';
          const origTime = record.interview_time || record.structured_evidence?.interview_time || '';

          const hasCalendarInvite = (record.attachment_count && record.attachment_count > 0) ||
            (record.timeline || []).some(t => {
              const p = (t.body_preview || '').toLowerCase();
              return p.includes('.ics') || p.includes('calendar') || p.includes('invite');
            });

          let detectedSourceLabel = '';
          if (origDate || origTime) {
            detectedSourceLabel = hasCalendarInvite ? 'Detected from calendar invite' : 'Detected from thread';
          }

          const isUnchangedFromDetected = Boolean(origDate) && (rescheduleDate === origDate) && (!origTime || rescheduleTime === origTime);
          const computedSource = isUnchangedFromDetected
            ? (hasCalendarInvite ? 'Scheduled from calendar invite' : 'Scheduled from thread')
            : 'Scheduled manually';

          return (
            <div>
              <h3 className="modal-title">Confirm Interview Status</h3>
              <p className="modal-subtitle">Select the verified status for this interview workflow:</p>

              <div className="modal-form-group">
                <label className="modal-label">Status Choice:</label>
                <CustomDropdown
                  options={[
                    { value: 'scheduled', label: 'Interview Scheduled' },
                    { value: 'completed', label: 'Completed (Starts 48h Feedback Timer)' },
                    { value: 'rescheduled', label: 'Rescheduled' },
                    { value: 'cancelled', label: 'Cancelled (Keeps Submission Open)' },
                    { value: 'not_confirmed', label: 'Not Confirmed (Keeps Submission Open)' },
                  ]}
                  value={interviewChoice}
                  onChange={val => setInterviewChoice(val)}
                  ariaLabel="Status Choice"
                />
              </div>

              {(interviewChoice === 'scheduled' || interviewChoice === 'rescheduled') && (
                <div className="modal-form-section">
                  {detectedSourceLabel && (
                    <p className="modal-detected-badge" style={{ color: 'var(--accent)', fontSize: '0.82rem', marginBottom: '8px' }}>
                      ℹ {detectedSourceLabel}
                    </p>
                  )}
                  <div className="modal-form-grid">
                    <div>
                      <label htmlFor="interview-modal-date" className="modal-label">{interviewChoice === 'rescheduled' ? 'New Date:' : 'Interview Date:'}</label>
                      <input
                        id="interview-modal-date"
                        type="date"
                        className="modal-input"
                        value={rescheduleDate}
                        onChange={e => setRescheduleDate(e.target.value)}
                      />
                    </div>
                    <div>
                      <label htmlFor="interview-modal-time" className="modal-label">{interviewChoice === 'rescheduled' ? 'New Time:' : 'Interview Time:'}</label>
                      <input
                        id="interview-modal-time"
                        type="time"
                        className="modal-input"
                        value={rescheduleTime}
                        onChange={e => setRescheduleTime(e.target.value)}
                      />
                    </div>
                    <div>
                      <label htmlFor="interview-modal-tz" className="modal-label">Timezone:</label>
                      <input
                        id="interview-modal-tz"
                        type="text"
                        className="modal-input"
                        value={rescheduleTz}
                        onChange={e => setRescheduleTz(e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              )}

              <div className="modal-actions">
                <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
                <button
                  className="btn-primary"
                  disabled={submitting || (interviewChoice === 'rescheduled' && !rescheduleDate)}
                  onClick={() =>
                    handleApiSubmit('interview-confirmation', {
                      choice: interviewChoice,
                      new_date: rescheduleDate || undefined,
                      new_time: rescheduleTime || undefined,
                      timezone: rescheduleTz || undefined,
                      source: interviewChoice === 'scheduled' ? computedSource : undefined,
                    })
                  }
                >
                  {submitting ? 'Confirming...' : 'Save Interview Status'}
                </button>
              </div>
              {errorMessage && (
                <div className="modal-error-under-save" role="alert" style={{ marginTop: '12px', color: '#ff6b6b', fontSize: '0.85rem', textAlign: 'center' }}>
                  ⚠️ {errorMessage}
                </div>
              )}
            </div>
          );
        })()}

        {/* Modal: Review Outcome */}
        {activeModal === 'review_outcome' && (
          <div>
            <h3 className="modal-title">Review Manager Action Outcome</h3>
            <p className="modal-subtitle">Detected requirement feedback/outcome requires manager review.</p>

            <div className="modal-form-group">
              <label className="modal-label">Manager Action Choice:</label>
              {(() => {
                const reviewOutcomeAction = (record as any).workflow?.allowed_actions?.find((a: any) => a.action_id === 'REVIEW_OUTCOME');
                const outcomeOpts = reviewOutcomeAction?.outcome_options;
                const options = outcomeOpts && outcomeOpts.length > 0
                  ? outcomeOpts.map((opt: any) => ({ value: opt.option_id, label: opt.label }))
                  : [
                      { value: 'POSITION_CLOSED', label: 'Position Closed' },
                      { value: 'CLIENT_REJECTED', label: 'Client Rejected' },
                      { value: 'CANDIDATE_WITHDRAWN', label: 'Candidate Withdrawn' },
                      { value: 'DUPLICATE_SUBMISSION', label: 'Duplicate Submission' },
                      { value: 'PLACED_JOINED', label: 'Placed / Joined' },
                      { value: 'NO_LONGER_AVAILABLE', label: 'No Longer Available' },
                      { value: 'NO_FOLLOW_UP_NEEDED', label: 'No Follow-up Needed' },
                      { value: 'OTHER_CLOSED', label: 'Other (Close)' },
                      { value: 'ON_HOLD', label: 'On Hold' },
                      { value: 'KEEP_IN_REVIEW', label: 'Keep in Review' },
                    ];
                return (
                  <CustomDropdown
                    options={options}
                    value={outcomeCategory}
                    onChange={setOutcomeCategory}
                    ariaLabel="Manager Action Choice"
                  />
                );
              })()}
            </div>

            <textarea
              className="modal-textarea"
              placeholder="Optional notes for outcome decision..."
              value={outcomeNotes}
              onChange={e => setOutcomeNotes(e.target.value)}
              rows={3}
            />

            <div className="modal-actions">
              <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
              <button
                className="btn-primary"
                disabled={submitting}
                onClick={() =>
                  handleApiSubmit('outcome-decision', {
                    outcome_category: outcomeCategory,
                    notes: outcomeNotes || undefined,
                  })
                }
              >
                {submitting ? 'Applying...' : 'Apply Decision'}
              </button>
            </div>
          </div>
        )}

        {/* Modal: Set Outcome */}
        {activeModal === 'set_outcome' && (
          <div>
            <h3 className="modal-title">Set Submission Outcome</h3>
            <p className="modal-subtitle">Assign authoritative category decision for this record.</p>

            <div className="modal-form-group">
              <label className="modal-label">Select Outcome:</label>
              <CustomDropdown
                options={[
                  { value: 'Interview Request', label: 'Interview Request' },
                  { value: 'Interview Scheduled', label: 'Interview Scheduled' },
                  { value: 'Position Closed', label: 'Position Closed' },
                  { value: 'Rejection', label: 'Rejection' },
                  { value: 'In Evaluation', label: 'In Evaluation' },
                  { value: 'Feedback', label: 'Feedback' },
                  { value: 'Duplicate / Already Submitted', label: 'Duplicate / Already Submitted' },
                  { value: 'Acknowledgement', label: 'Acknowledgement' },
                  { value: 'No Response', label: 'No Response' },
                  { value: 'Unrelated', label: 'Unrelated' },
                  { value: 'Keep in Needs Review', label: 'Keep in Needs Review' },
                ]}
                value={outcomeCategory}
                onChange={setOutcomeCategory}
                ariaLabel="Select Outcome"
              />
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
              <button
                className="btn-primary"
                disabled={submitting}
                onClick={() =>
                  handleApiSubmit('outcome-decision', {
                    outcome_category: outcomeCategory,
                  })
                }
              >
                {submitting ? 'Setting...' : 'Set Outcome'}
              </button>
            </div>
          </div>
        )}

        {/* Modal: Close Record */}
        {activeModal === 'close' && (
          <div>
            <h3 className="modal-title">Close Submission Record</h3>
            <p className="modal-subtitle">Closing preserves history locally without modifying Outlook content.</p>

            <div className="modal-form-group">
              <label className="modal-label">Close Reason:</label>
              {(() => {
                const closeAction = (record as any).workflow?.allowed_actions?.find((a: any) => a.action_id === 'CLOSE_RECORD');
                const reasonOpts = closeAction?.reason_options;
                const options = reasonOpts && reasonOpts.length > 0
                  ? reasonOpts.map((r: any) => ({ value: r, label: r }))
                  : [
                      { value: 'Position closed', label: 'Position closed' },
                      { value: 'Candidate withdrawn', label: 'Candidate withdrawn' },
                      { value: 'Client rejected', label: 'Client rejected' },
                      { value: 'No follow-up needed', label: 'No follow-up needed' },
                      { value: 'Other', label: 'Other' },
                    ];
                return (
                  <CustomDropdown
                    options={options}
                    value={closeReason}
                    onChange={setCloseReason}
                    ariaLabel="Close Reason"
                  />
                );
              })()}
            </div>

            {closeReason === 'Other' && (
              <textarea
                className="modal-textarea"
                placeholder="Required note for 'Other' close reason..."
                value={closeNote}
                onChange={e => setCloseNote(e.target.value)}
                rows={3}
              />
            )}

            <div className="modal-actions">
              <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
              <button
                className="btn-danger"
                disabled={submitting || (closeReason === 'Other' && !closeNote.trim())}
                onClick={() =>
                  handleApiSubmit('close', {
                    reason: closeReason,
                    close_note: closeNote || undefined,
                  })
                }
              >
                {submitting ? 'Closing...' : 'Close Record'}
              </button>
            </div>
          </div>
        )}

        {/* Modal: Reopen Record */}
        {activeModal === 'reopen' && (
          <div>
            <h3 className="modal-title">Reopen Submission Record</h3>
            <p className="modal-subtitle">Reopens this closed record into Needs Review for active management.</p>

            <textarea
              className="modal-textarea"
              placeholder="Optional reason for reopening..."
              value={reopenReason}
              onChange={e => setReopenReason(e.target.value)}
              rows={2}
            />

            <div className="modal-actions">
              <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
              <button
                className="btn-primary"
                disabled={submitting}
                onClick={() =>
                  handleApiSubmit('reopen', {
                    reason: reopenReason || undefined,
                  })
                }
              >
                {submitting ? 'Reopening...' : 'Confirm Reopen'}
              </button>
            </div>
          </div>
        )}

        {/* Modal: Link Interview Conversation */}
        {activeModal === 'link-interview' && (
          <div>
            <h3 className="modal-title">Confirm Link: Related Interview Conversation</h3>
            <p className="modal-subtitle">
              Link this separate interview conversation to the submission record. Linking enables interview workflow and timers while preserving the original submission chain for follow-ups.
            </p>

            {(() => {
              const sugg = selectedSuggestion || (record.interview_suggestions && record.interview_suggestions[0]);
              if (!sugg) return <p>No suggestion available to link.</p>;

              return (
                <div className="modal-evidence-box" style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '6px', marginBottom: '1rem', border: '1px solid #e2e8f0', fontSize: '0.875rem' }}>
                  <div style={{ marginBottom: '0.5rem' }}><strong>Candidate:</strong> {sugg.candidate_name || record.candidate_name || 'N/A'}</div>
                  {sugg.job_id && <div style={{ marginBottom: '0.5rem' }}><strong>Job ID:</strong> {sugg.job_id}</div>}
                  {sugg.ep_reference && <div style={{ marginBottom: '0.5rem' }}><strong>EP Reference:</strong> {sugg.ep_reference}</div>}
                  <div style={{ marginBottom: '0.5rem' }}>
                    <strong>Original Submission:</strong> {sugg.submission_subject || 'N/A'} {sugg.submission_received_at ? `(${formatTimestamp(sugg.submission_received_at)})` : ''}
                  </div>
                  <div style={{ marginBottom: '0.5rem' }}>
                    <strong>Proposed Interview Conversation:</strong> {sugg.interview_subject || 'N/A'} {sugg.interview_received_at ? `(${formatTimestamp(sugg.interview_received_at)})` : ''}
                  </div>
                  {(() => {
                    const lastMsg = (sugg.thread_messages && sugg.thread_messages[sugg.thread_messages.length - 1]);
                    const sender = sugg.latest_interview_message_sender || lastMsg?.from?.emailAddress?.address || (lastMsg as any)?.sender;
                    const excerpt = sugg.latest_interview_message_excerpt || lastMsg?.bodyPreview || (lastMsg as any)?.body_preview;

                    return (
                      <>
                        {sender && (
                          <div style={{ marginBottom: '0.5rem' }}>
                            <strong>Latest Interview Sender:</strong> {sender}
                          </div>
                        )}
                        {excerpt && (
                          <div style={{ marginTop: '0.5rem', padding: '0.5rem', backgroundColor: '#ffffff', borderRadius: '4px', border: '1px solid #cbd5e1' }}>
                            <strong>Latest Message Excerpt:</strong>
                            <p style={{ margin: '0.25rem 0 0 0', fontStyle: 'italic' }}>"{excerpt}"</p>
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              );
            })()}

            <div className="modal-actions">
              <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
              <button
                className="btn-primary"
                disabled={submitting || (!selectedSuggestion && (!record.interview_suggestions || record.interview_suggestions.length === 0))}
                onClick={() => {
                  const sugg = selectedSuggestion || (record.interview_suggestions && record.interview_suggestions[0]);
                  if (!sugg) return;
                  handleApiSubmit('link-interview', {
                    linked_conversation_id: sugg.conversation_id,
                    interview_subject: sugg.interview_subject,
                    interview_received_at: sugg.interview_received_at,
                    thread_messages: sugg.thread_messages || []
                  });
                }}
              >
                {submitting ? 'Linking...' : 'Confirm Link'}
              </button>
            </div>
          </div>
        )}

        {/* Modal: Unlink Interview Conversation */}
        {activeModal === 'unlink-interview' && (
          <div>
            <h3 className="modal-title">Unlink Interview Conversation</h3>
            <p className="modal-subtitle">
              Are you sure you want to unlink this interview conversation from the submission record? Classification and status will re-evaluate based strictly on the original submission conversation.
            </p>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
              <button
                className="btn-danger"
                disabled={submitting || (!selectedLinked && (!record.linked_conversations || record.linked_conversations.length === 0))}
                onClick={() => {
                  const lc = selectedLinked || (record.linked_conversations && record.linked_conversations[0]);
                  if (!lc) return;
                  handleApiSubmit('unlink-interview', {
                    linked_conversation_id: lc.conversation_id
                  });
                }}
              >
                {submitting ? 'Unlinking...' : 'Confirm Unlink'}
              </button>
            </div>
          </div>
        )}

        {/* Modal: Status Action Confirmation */}
        {activeModal && activeModal.startsWith('action_') && (() => {
          const actionMap: Record<string, { title: string; endpoint: string; outcomeCat?: string; isClose?: boolean; defaultReasons: string[] }> = {
            action_closed: {
              title: 'Mark Position Closed',
              endpoint: 'outcome-decision',
              outcomeCat: 'Position Closed',
              defaultReasons: ['Client confirmed position is closed', 'Requirement filled by another vendor', 'Client cancelled requisition', 'Other']
            },
            action_rejected: {
              title: 'Mark Candidate Rejected',
              endpoint: 'outcome-decision',
              outcomeCat: 'Client Rejected',
              defaultReasons: ['Candidate profile not selected', 'Failed technical evaluation', 'Client declined to move forward', 'Other']
            },
            action_withdrawn: {
              title: 'Mark Candidate Withdrawn',
              endpoint: 'close',
              isClose: true,
              outcomeCat: 'Candidate withdrawn',
              defaultReasons: ['Candidate accepted another offer', 'Candidate no longer interested', 'Salary/Rate mismatch', 'Other']
            },
            action_duplicate: {
              title: 'Mark Duplicate Submission',
              endpoint: 'close',
              isClose: true,
              outcomeCat: 'Duplicate submission',
              defaultReasons: ['Candidate already submitted by another vendor', 'Duplicate submission entry', 'Other']
            },
            action_on_hold: {
              title: 'Mark On Hold',
              endpoint: 'close',
              isClose: true,
              outcomeCat: 'On hold',
              defaultReasons: ['Client placed req on hold', 'Budget/headcount hold', 'Other']
            },
            action_placed: {
              title: 'Mark Placed / Joined',
              endpoint: 'close',
              isClose: true,
              outcomeCat: 'Placed / joined',
              defaultReasons: ['Candidate selected and offer accepted', 'Candidate joined client project', 'Other']
            },
            action_unavailable: {
              title: 'Mark No Longer Available',
              endpoint: 'close',
              isClose: true,
              outcomeCat: 'No longer available',
              defaultReasons: ['Candidate unavailable for start date', 'Location/travel mismatch', 'Other']
            },
            action_schedule: {
              title: 'Schedule Next Follow-up',
              endpoint: 'review-deferral',
              defaultReasons: ['Follow up scheduled after client review', 'Waiting for candidate availability', 'Other']
            }
          };

          const config = actionMap[activeModal] || {
            title: 'Confirm Action',
            endpoint: 'outcome-decision',
            outcomeCat: 'Move to Needs Review',
            defaultReasons: ['Manager request', 'Other']
          };

          const currentStatusLabel = getDisplayLabel(record.domain_status, record.thread_message_count, record.structured_evidence?.category);

          return (
            <div>
              <h3 className="modal-title">{config.title}</h3>
              <p className="modal-subtitle">Confirm status change for this submission. Audit trail will be recorded.</p>

              {/* Confirmation Details Card */}
              <div className="modal-evidence-box" style={{ backgroundColor: '#f8fafc', padding: '0.85rem 1rem', borderRadius: '6px', marginBottom: '1rem', border: '1px solid #e2e8f0', fontSize: '0.85rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                  <div><strong>Candidate:</strong> {record.candidate_name || '—'}</div>
                  <div><strong>Job ID:</strong> {record.job_id || '—'}</div>
                  <div><strong>Current Status:</strong> <span style={{ fontWeight: 600 }}>{currentStatusLabel}</span></div>
                  <div><strong>New Action:</strong> <span style={{ fontWeight: 600, color: 'var(--accent, #0284c7)' }}>{config.title}</span></div>
                </div>
              </div>

              {/* Reason Selector (Required) */}
              <div className="modal-form-group">
                <label className="modal-label" htmlFor="action-reason-input">Select Reason <span style={{ color: '#ef4444' }}>*</span>:</label>
                <CustomDropdown
                  options={config.defaultReasons.map(r => ({ value: r, label: r }))}
                  value={actionReason}
                  onChange={val => setActionReason(val)}
                  ariaLabel="Select Action Reason"
                />
              </div>

              {/* Optional Note */}
              <div className="modal-form-group">
                <label className="modal-label" htmlFor="action-note-input">Optional Note:</label>
                <textarea
                  id="action-note-input"
                  className="modal-textarea"
                  placeholder="Enter optional notes for audit trail..."
                  value={actionNote}
                  onChange={e => setActionNote(e.target.value)}
                  rows={2}
                />
              </div>

              <div className="modal-actions">
                <button className="btn-secondary" onClick={onCloseModal} disabled={submitting}>Cancel</button>
                <button
                  className="btn-primary"
                  disabled={submitting || !actionReason.trim()}
                  onClick={() => {
                    if (config.isClose) {
                      handleApiSubmit('close', {
                        reason: actionReason,
                        close_note: actionNote ? actionNote : undefined
                      });
                    } else if (config.endpoint === 'review-deferral') {
                      const nextDay = new Date(Date.now() + 86400000 * 2).toISOString();
                      handleApiSubmit('review-deferral', {
                        review_after: nextDay,
                        reason: actionReason + (actionNote ? ` — ${actionNote}` : '')
                      });
                    } else {
                      handleApiSubmit('outcome-decision', {
                        outcome_category: config.outcomeCat || 'Position Closed',
                        notes: actionReason + (actionNote ? ` — ${actionNote}` : '')
                      });
                    }
                  }}
                >
                  {submitting ? 'Updating...' : 'Confirm Status Change'}
                </button>
              </div>
              {errorMessage && (
                <div role="alert" style={{ marginTop: '12px', color: '#ff6b6b', fontSize: '0.85rem', textAlign: 'center' }}>
                  ⚠️ {errorMessage}
                </div>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}
