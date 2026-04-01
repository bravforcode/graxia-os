"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-04-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # opportunities
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("source_url", sa.Text),
        sa.Column("source_platform", sa.String(100)),
        sa.Column("deadline", sa.Date),
        sa.Column("application_open", sa.Date),
        sa.Column("money_score", sa.SmallInteger),
        sa.Column("brand_score", sa.SmallInteger),
        sa.Column("network_score", sa.SmallInteger),
        sa.Column("startup_score", sa.SmallInteger),
        sa.Column("effort_score", sa.SmallInteger),
        sa.Column("total_score", sa.Numeric(4, 2)),
        sa.Column("scoring_rationale", sa.Text),
        sa.Column("red_flags", postgresql.JSONB, server_default="[]"),
        sa.Column("decision", sa.String(20)),
        sa.Column("decision_confidence", sa.Numeric(3, 2)),
        sa.Column("decision_reasoning", sa.Text),
        sa.Column("decision_factors", postgresql.JSONB, server_default="{}"),
        sa.Column("review_after", sa.Date),
        sa.Column("conviction_score", sa.SmallInteger),
        sa.Column("user_notes", sa.Text),
        sa.Column("status", sa.String(50), server_default="found"),
        sa.Column("prize_amount", sa.String(300)),
        sa.Column("prize_currency", sa.String(10)),
        sa.Column("requirements", postgresql.JSONB, server_default="[]"),
        sa.Column("tags", postgresql.JSONB, server_default="[]"),
        sa.Column("is_team_allowed", sa.Boolean),
        sa.Column("max_team_size", sa.Integer),
        sa.Column("is_student_eligible", sa.Boolean),
        sa.Column("location_type", sa.String(30)),
        sa.Column("fit_summary", sa.Text),
        sa.Column("action_priority", sa.String(20)),
        sa.Column("raw_data", postgresql.JSONB, server_default="{}"),
        sa.Column("found_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("acted_on_at", sa.DateTime(timezone=True)),
        sa.Column("source_hash", sa.String(64)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_hash"),
        sa.CheckConstraint("type IN ('freelance','competition','hackathon','grant','accelerator','fellowship','job','other')", name="ck_opp_type"),
        sa.CheckConstraint("money_score BETWEEN 0 AND 10", name="ck_opp_money_score"),
        sa.CheckConstraint("brand_score BETWEEN 0 AND 10", name="ck_opp_brand_score"),
        sa.CheckConstraint("network_score BETWEEN 0 AND 10", name="ck_opp_network_score"),
        sa.CheckConstraint("startup_score BETWEEN 0 AND 10", name="ck_opp_startup_score"),
        sa.CheckConstraint("effort_score BETWEEN 0 AND 10", name="ck_opp_effort_score"),
        sa.CheckConstraint("decision IN ('do_now','delay','skip','ask_user')", name="ck_opp_decision"),
        sa.CheckConstraint("conviction_score BETWEEN 1 AND 10", name="ck_opp_conviction"),
        sa.CheckConstraint("status IN ('found','scored','decided','reviewed','approved','in_progress','applied','waiting','accepted','rejected','withdrawn','ignored')", name="ck_opp_status"),
        sa.CheckConstraint("location_type IN ('online','thailand','asean','global')", name="ck_opp_location_type"),
        sa.CheckConstraint("action_priority IN ('do_now','queue','skip')", name="ck_opp_action_priority"),
    )
    op.create_index("idx_opps_status", "opportunities", ["status"])
    op.create_index("idx_opps_score", "opportunities", [sa.text("total_score DESC NULLS LAST")])
    op.create_index("idx_opps_type", "opportunities", ["type"])
    op.create_index("idx_opps_priority", "opportunities", ["action_priority"], postgresql_where=sa.text("action_priority = 'do_now'"))
    op.create_index("idx_opps_decision", "opportunities", ["decision"], postgresql_where=sa.text("decision = 'do_now'"))

    # contacts
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("role", sa.String(200)),
        sa.Column("company", sa.String(300)),
        sa.Column("contact_type", sa.String(50)),
        sa.Column("linkedin_url", sa.Text),
        sa.Column("email", sa.String(300)),
        sa.Column("telegram_handle", sa.String(200)),
        sa.Column("github_handle", sa.String(200)),
        sa.Column("other_channels", postgresql.JSONB, server_default="{}"),
        sa.Column("relationship_strength", sa.SmallInteger, server_default="1"),
        sa.Column("last_contacted_at", sa.Date),
        sa.Column("next_followup_date", sa.Date),
        sa.Column("followup_reason", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("conversation_summary", sa.Text),
        sa.Column("met_at", sa.String(300)),
        sa.Column("referred_by", postgresql.UUID(as_uuid=True)),
        sa.Column("value_score", sa.SmallInteger),
        sa.Column("network_cluster", sa.String(100)),
        sa.Column("is_bridge_node", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["referred_by"], ["contacts.id"]),
        sa.CheckConstraint("contact_type IN ('client','lead','mentor','founder','investor','recruiter','collaborator','event_organizer','other')", name="ck_contact_type"),
        sa.CheckConstraint("relationship_strength BETWEEN 1 AND 5", name="ck_contact_rel_strength"),
        sa.CheckConstraint("value_score BETWEEN 1 AND 10", name="ck_contact_value_score"),
    )
    op.create_index("idx_contacts_followup", "contacts", ["next_followup_date"], postgresql_where=sa.text("next_followup_date IS NOT NULL"))
    op.create_index("idx_contacts_type", "contacts", ["contact_type"])
    op.create_index("idx_contacts_cluster", "contacts", ["network_cluster"])

    # contact_edges
    op.create_table(
        "contact_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("from_contact_id", postgresql.UUID(as_uuid=True)),
        sa.Column("to_contact_id", postgresql.UUID(as_uuid=True)),
        sa.Column("edge_type", sa.String(50)),
        sa.Column("strength", sa.SmallInteger, server_default="3"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["from_contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("from_contact_id", "to_contact_id", "edge_type", name="uq_edge"),
        sa.CheckConstraint("edge_type IN ('referred','worked_with','mentor_of','organizes','knows','invested_in','co_founded')", name="ck_edge_type"),
        sa.CheckConstraint("strength BETWEEN 1 AND 5", name="ck_edge_strength"),
    )
    op.create_index("idx_edges_from", "contact_edges", ["from_contact_id"])
    op.create_index("idx_edges_to", "contact_edges", ["to_contact_id"])

    # submissions
    op.create_table(
        "submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True)),
        sa.Column("type", sa.String(50)),
        sa.Column("title", sa.String(500)),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("content", sa.Text),
        sa.Column("subject_line", sa.String(500)),
        sa.Column("attachments", postgresql.JSONB, server_default="[]"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("replied_at", sa.DateTime(timezone=True)),
        sa.Column("follow_up_date", sa.Date),
        sa.Column("outcome_at", sa.DateTime(timezone=True)),
        sa.Column("outcome_notes", sa.Text),
        sa.Column("proposed_value", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(10), server_default="THB"),
        sa.Column("actual_value", sa.Numeric(12, 2)),
        sa.Column("lost_reason_primary", sa.String(50)),
        sa.Column("lost_reason_secondary", sa.String(50)),
        sa.Column("lost_stage", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.CheckConstraint("type IN ('outreach_dm','application','proposal','follow_up','interview_prep')", name="ck_sub_type"),
        sa.CheckConstraint("status IN ('draft','approved','sent','opened','replied','meeting_scheduled','negotiating','won','lost','withdrawn')", name="ck_sub_status"),
        sa.CheckConstraint("lost_reason_primary IN ('no_reply','too_expensive','weak_fit','weak_message','timing_bad','stronger_competitor','deadline_missed','unclear_scope','student_status_disadvantage','other','unknown')", name="ck_sub_lost_reason"),
        sa.CheckConstraint("lost_stage IN ('no_contact','initial_reply','proposal','negotiation','final_decision','unknown')", name="ck_sub_lost_stage"),
    )
    op.create_index("idx_submissions_status", "submissions", ["status"])
    op.create_index("idx_submissions_followup", "submissions", ["follow_up_date"], postgresql_where=sa.text("follow_up_date IS NOT NULL"))
    op.create_index("idx_submissions_lost_reason", "submissions", ["lost_reason_primary"], postgresql_where=sa.text("status = 'lost'"))

    # content_drafts
    op.create_table(
        "content_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("type", sa.String(50)),
        sa.Column("title", sa.String(500)),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("context_notes", sa.Text),
        sa.Column("review_notes", sa.Text),
        sa.Column("status", sa.String(30), server_default="pending"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("revision_request", sa.Text),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True)),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True)),
        sa.Column("model_used", sa.String(100)),
        sa.Column("generation_tokens", sa.Integer),
        sa.Column("generation_cost_usd", sa.Numeric(8, 6)),
        sa.Column("used_playbook_ids", postgresql.JSONB, server_default="[]"),
        sa.Column("was_fallback_draft", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.CheckConstraint("type IN ('proposal','linkedin_post','outreach_dm','follow_up','application_essay','cv_update','bio_update','other')", name="ck_draft_type"),
        sa.CheckConstraint("status IN ('pending','approved','rejected','sent','revised')", name="ck_draft_status"),
    )
    op.create_index("idx_drafts_pending", "content_drafts", ["created_at"], postgresql_where=sa.text("status = 'pending'"))

    # knowledge_items
    op.create_table(
        "knowledge_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("category", sa.String(50)),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tags", postgresql.JSONB, server_default="[]"),
        sa.Column("best_for", postgresql.JSONB, server_default="[]"),
        sa.Column("project_url", sa.Text),
        sa.Column("github_url", sa.Text),
        sa.Column("tech_stack", postgresql.JSONB, server_default="[]"),
        sa.Column("metrics_achieved", sa.Text),
        sa.Column("use_count", sa.Integer, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("approval_rate_when_used", sa.Numeric(5, 2)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("category IN ('project','proposal_template','bio','skill_description','lesson','case_study','testimonial','pitch_snippet','objection_response','playbook','failure_analysis')", name="ck_knowledge_category"),
    )

    # outcome_patterns
    op.create_table(
        "outcome_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True)),
        sa.Column("opportunity_type", sa.String(50)),
        sa.Column("client_type", sa.String(50)),
        sa.Column("money_score", sa.SmallInteger),
        sa.Column("brand_score", sa.SmallInteger),
        sa.Column("network_score", sa.SmallInteger),
        sa.Column("startup_score", sa.SmallInteger),
        sa.Column("effort_score", sa.SmallInteger),
        sa.Column("total_score", sa.Numeric(4, 2)),
        sa.Column("decision_at_time", sa.String(20)),
        sa.Column("conviction_score_at_time", sa.SmallInteger),
        sa.Column("energy_at_time", sa.SmallInteger),
        sa.Column("outcome", sa.String(20)),
        sa.Column("actual_value_thb", sa.Numeric(12, 2)),
        sa.Column("lost_reason", sa.String(50)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.CheckConstraint("outcome IN ('positive','negative','neutral')", name="ck_outcome"),
    )

    # cognitive_state
    op.create_table(
        "cognitive_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("date", sa.Date, nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("energy", sa.SmallInteger, server_default="7"),
        sa.Column("stress", sa.SmallInteger, server_default="3"),
        sa.Column("available_hours_this_week", sa.Integer, server_default="20"),
        sa.Column("exam_pressure", sa.SmallInteger, server_default="0"),
        sa.Column("mood_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date"),
        sa.CheckConstraint("energy BETWEEN 0 AND 10", name="ck_cog_energy"),
        sa.CheckConstraint("stress BETWEEN 0 AND 10", name="ck_cog_stress"),
        sa.CheckConstraint("exam_pressure BETWEEN 0 AND 10", name="ck_cog_exam"),
    )

    # scoring_weight_history
    op.create_table(
        "scoring_weight_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("weights", postgresql.JSONB, nullable=False),
        sa.Column("previous_weights", postgresql.JSONB),
        sa.Column("changed_by", sa.String(50)),
        sa.Column("change_reason", sa.Text),
        sa.Column("confidence_at_change", sa.Numeric(3, 2)),
        sa.Column("data_points_analyzed", sa.Integer),
        sa.Column("is_current", sa.Boolean, server_default="true"),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("changed_by IN ('user','learning_engine','rollback')", name="ck_weight_changed_by"),
    )
    op.create_index("idx_weights_current", "scoring_weight_history", ["is_current"], postgresql_where=sa.text("is_current = TRUE"))

    # scraper_health
    op.create_table(
        "scraper_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer, server_default="0"),
        sa.Column("total_runs", sa.Integer, server_default="0"),
        sa.Column("total_successes", sa.Integer, server_default="0"),
        sa.Column("success_rate", sa.Numeric(5, 2)),
        sa.Column("is_muted", sa.Boolean, server_default="false"),
        sa.Column("muted_until", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("avg_items_per_run", sa.Numeric(8, 2)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_name"),
    )

    # identity_snapshots
    op.create_table(
        "identity_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("positioning_label", sa.String(200)),
        sa.Column("profile_hash", sa.String(64)),
        sa.Column("key_skills", postgresql.JSONB, server_default="[]"),
        sa.Column("primary_narrative", sa.Text),
        sa.Column("revenue_at_snapshot", sa.Numeric(12, 2)),
        sa.Column("competitions_won_at_snapshot", sa.Integer),
        sa.Column("change_trigger", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # weekly_metrics
    op.create_table(
        "weekly_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("opps_found", sa.Integer, server_default="0"),
        sa.Column("opps_scored", sa.Integer, server_default="0"),
        sa.Column("opps_decided", sa.Integer, server_default="0"),
        sa.Column("opps_actioned", sa.Integer, server_default="0"),
        sa.Column("opps_ignored", sa.Integer, server_default="0"),
        sa.Column("outreach_sent", sa.Integer, server_default="0"),
        sa.Column("outreach_replied", sa.Integer, server_default="0"),
        sa.Column("reply_rate", sa.Numeric(5, 2)),
        sa.Column("meetings_booked", sa.Integer, server_default="0"),
        sa.Column("proposals_sent", sa.Integer, server_default="0"),
        sa.Column("proposals_won", sa.Integer, server_default="0"),
        sa.Column("close_rate", sa.Numeric(5, 2)),
        sa.Column("revenue_thb", sa.Numeric(12, 2), server_default="0"),
        sa.Column("pipeline_value_thb", sa.Numeric(12, 2), server_default="0"),
        sa.Column("comps_found", sa.Integer, server_default="0"),
        sa.Column("comps_applied", sa.Integer, server_default="0"),
        sa.Column("comps_results", sa.Integer, server_default="0"),
        sa.Column("ai_cost_usd", sa.Numeric(8, 4), server_default="0"),
        sa.Column("tasks_completed", sa.Integer, server_default="0"),
        sa.Column("tasks_failed", sa.Integer, server_default="0"),
        sa.Column("scraper_success_rate", sa.Numeric(5, 2)),
        sa.Column("decision_accuracy_score", sa.Numeric(5, 2)),
        sa.Column("avg_energy_this_week", sa.Numeric(4, 2)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("week_start"),
    )

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("entity_type", sa.String(100)),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("details", postgresql.JSONB, server_default="{}"),
        sa.Column("triggered_by", sa.String(100)),
        sa.Column("success", sa.Boolean, server_default="true"),
        sa.Column("error_message", sa.Text),
        sa.Column("ai_model_used", sa.String(100)),
        sa.Column("was_fallback", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_created", "audit_log", [sa.text("created_at DESC")])
    op.create_index("idx_audit_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("weekly_metrics")
    op.drop_table("identity_snapshots")
    op.drop_table("scraper_health")
    op.drop_table("scoring_weight_history")
    op.drop_table("cognitive_state")
    op.drop_table("outcome_patterns")
    op.drop_table("knowledge_items")
    op.drop_table("content_drafts")
    op.drop_table("submissions")
    op.drop_table("contact_edges")
    op.drop_table("contacts")
    op.drop_table("opportunities")
