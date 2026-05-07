import { z } from 'zod';

export const DeliverableContractSchema = z.object({
  type: z.string(),
  format: z.string(),
  review_required: z.boolean().default(true),
  acceptance_criteria: z.array(z.string()),
});

export const EscalationPolicySchema = z.object({
  if_blocked: z.string().default('notify_chief_of_staff'),
  if_overdue: z.string().default('notify_ceo'),
  if_error: z.string().default('notify_engineer_agent'),
});

export const MessageEnvelopeSchema = z.object({
  message_id: z.string(),
  thread_id: z.string(),
  mission_id: z.string(),
  task_id: z.string(),
  parent_task_id: z.string().optional(),
  from_agent: z.string(),
  to_agent: z.string(),
  message_type: z.string(),
  priority: z.enum(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']).default('MEDIUM'),
  risk_class: z.enum(['CLASS_0', 'CLASS_1', 'CLASS_2', 'CLASS_3', 'CLASS_4', 'CLASS_5']).default('CLASS_1'),
  budget_limit_usd: z.number().default(0),
  deadline_at: z.string().datetime(),
  sla_minutes: z.number().default(60),
  tool_scope: z.array(z.string()).default([]),
  skill_scope: z.array(z.string()).default([]),
  requires_approval: z.boolean().default(false),
  confidence: z.number().min(0).max(1).default(1),
  deliverable_contract: DeliverableContractSchema.optional(),
  escalation: EscalationPolicySchema,
  correlation_id: z.string(),
  trace_id: z.string(),
  payload: z.record(z.any()).default({}),
  created_at: z.string().datetime().default(() => new Date().toISOString()),
});

export type MessageEnvelope = z.infer<typeof MessageEnvelopeSchema>;
