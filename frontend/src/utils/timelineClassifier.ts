// Timeline classification utilities — single source of truth.
// Extracted from RecordWorkspace so both components and tests can import.

import type { TimelineEntry, FullRecord } from '../types';

// --- Timeline classification ---
// RULES:
// 1. Original Submission = entry.graph_immutable_id === record.graph_immutable_id
// 2. Manager Follow-up = only with authoritative classification
// 3. Sent Message = from manager domain, no authoritative follow-up
// 4. Inbound Response = external sender
// 5. Automatic Reply = deterministic sender/body detection
// 6. Message = unknown/ambiguous (never a guessed business label)

export interface TimelineInfo { className: string; label: string }

export function getTimelineInfo(entry: TimelineEntry, record: FullRecord): TimelineInfo {
  if (entry.is_system_note) {
    return { className: 'timeline-system', label: 'System Note' };
  }

  if (entry.role === 'interview_coordination') {
    return { className: 'timeline-interview', label: 'Linked Interview' };
  }

  if (entry.graph_immutable_id && entry.graph_immutable_id === record.graph_immutable_id) {
    return { className: 'timeline-submission', label: 'Original Submission' };
  }

  const sender = (entry.sender || '').toLowerCase();

  if (isAutomaticReply(sender, entry.body_preview || '')) {
    return { className: 'timeline-auto', label: 'Automatic Reply' };
  }

  if (sender.includes('@clifyx.com')) {
    if (entry.classification && /follow.?up|manager_follow/i.test(entry.classification)) {
      return { className: 'timeline-followup', label: 'Manager Follow-up' };
    }
    return { className: 'timeline-sent', label: 'Sent Message' };
  }

  if (sender && sender.includes('@')) {
    return { className: 'timeline-inbound', label: 'Inbound Response' };
  }

  return { className: 'timeline-unknown', label: 'Message' };
}

export function isAutomaticReply(sender: string, body: string): boolean {
  const autoSenders = ['noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'mailer-daemon', 'postmaster', 'auto-notify', 'notifications@'];
  if (autoSenders.some(p => sender.includes(p))) return true;

  const bodyLower = body.toLowerCase();
  const autoPatterns = [
    'automatic reply', 'auto-reply', 'auto reply',
    'out of office', 'out-of-office',
    'this is an automated message', 'this is an automatic',
    'do not reply to this message',
  ];
  return autoPatterns.some(p => bodyLower.includes(p));
}

// --- Participant extraction ---

export interface Participant { role: string; address: string }

export function collectParticipants(timeline: TimelineEntry[]): Participant[] {
  const seen = new Set<string>();
  const result: Participant[] = [];
  for (const entry of timeline) {
    if (entry.sender && !seen.has(entry.sender)) {
      seen.add(entry.sender);
      result.push({ role: 'Sender', address: entry.sender });
    }
    for (const addr of entry.to_recipients || []) {
      if (!seen.has(addr)) {
        seen.add(addr);
        result.push({ role: 'To', address: addr });
      }
    }
    for (const addr of entry.cc_recipients || []) {
      if (!seen.has(addr)) {
        seen.add(addr);
        result.push({ role: 'CC', address: addr });
      }
    }
    // Never show BCC
  }
  return result;
}

// --- Due status formatting ---

export function formatDueStatus(feedbackDueAt: string): string {
  try {
    const due = new Date(feedbackDueAt);
    const now = new Date();
    const diffMs = due.getTime() - now.getTime();
    const diffH = Math.round(diffMs / 3600000);
    if (diffH < 0) return `Overdue by ${Math.abs(diffH)}h`;
    if (diffH <= 6) return `${diffH}h remaining (urgent)`;
    return `${diffH}h remaining`;
  } catch { return '—'; }
}
