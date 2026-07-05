import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # 255 (not the old 128): Werkzeug's default hashing method is now scrypt,
    # whose encoded output (~162 chars) no longer fits in 128 — inserting one
    # raised "String or binary data would be truncated" on SQL Server.
    password_hash = db.Column(db.String(255), nullable=True) # Nullable for Xero SSO only users
    
    # Xero Integration attributes
    xero_user_id = db.Column(db.String(100), unique=True, nullable=True)
    xero_token_data = db.Column(db.Text, nullable=True) # Store JSON token dict string

    # 'staff' (default) can only see their own review history; 'partner' can
    # see the firm-wide client overview across all staff; 'client' is a
    # restricted business-owner login, scoped to whatever tenants are granted
    # via ClientAccess (see below) rather than a Xero OAuth connection.
    role = db.Column(db.String(20), default='staff', nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to historical notes
    review_notes = db.relationship('ReviewNote', backref='user', lazy=True)

    def set_xero_token(self, token_dict: dict):
        self.xero_token_data = json.dumps(token_dict)

    def get_xero_token(self) -> dict:
        if self.xero_token_data:
            return json.loads(self.xero_token_data)
        return None

    @property
    def is_partner(self) -> bool:
        return self.role == 'partner'

    @property
    def is_client(self) -> bool:
        return self.role == 'client'

class ReviewNote(db.Model):
    __tablename__ = 'review_notes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    tenant_id = db.Column(db.String(100), nullable=False)
    tenant_name = db.Column(db.String(200), nullable=True)
    
    run_id = db.Column(db.String(100), unique=True, nullable=False) # Maps to the .jsonl/csv run
    
    year_start = db.Column(db.String(20), nullable=True)
    year_end = db.Column(db.String(20), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='COMPLETED')


class ClientAccess(db.Model):
    """Grants a 'client' role User read/complete access to one tenant."""
    __tablename__ = 'client_access'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    tenant_id = db.Column(db.String(100), nullable=False)
    # Cached so the client's own dashboard never needs a Xero call (they have no token).
    tenant_name = db.Column(db.String(200), nullable=True)

    granted_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='client_accesses')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'tenant_id', name='uq_client_access_user_tenant'),
    )


class Plan(db.Model):
    """A standardized, editable action-item list for one client (tenant)."""
    __tablename__ = 'plans'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(100), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='active', nullable=False)  # 'active' | 'inactive'

    source_review_note_id = db.Column(db.Integer, db.ForeignKey('review_notes.id'), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source_review_note = db.relationship('ReviewNote')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    steps = db.relationship(
        'PlanStep', backref='plan', lazy=True,
        order_by='PlanStep.position', cascade='all, delete-orphan',
    )

    @property
    def is_active(self) -> bool:
        return self.status == 'active'


class PlanStep(db.Model):
    """One action item within a Plan. Completion here is what feeds the Timeline."""
    __tablename__ = 'plan_steps'
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # 'pending' | 'done'

    completed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    completion_note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    completed_by = db.relationship('User', foreign_keys=[completed_by_user_id])

    @property
    def is_done(self) -> bool:
        return self.status == 'done'


class ChatSession(db.Model):
    """One chat conversation for a (user, tenant) pair on the Chat page.

    A user can have many sessions per tenant (shown as chat history); there's
    no 'active' notion anymore — whichever session_id the page has open is
    current, and no code in this app reads `status`.

    The column itself is kept (always 'active') purely for database
    compatibility: production runs on Azure SQL under a non-default schema
    (DATABASE_SCHEMA), where this table was originally created with a
    NOT NULL status column. This app has no migration tooling — only
    db.create_all(), which never alters an existing table — and an
    app-tier SQL login commonly lacks ALTER TABLE rights anyway, so trying
    to drop the column in-place isn't reliable. Simplest correct fix: always
    populate it so the constraint is satisfied everywhere, old and new DBs
    alike, with zero DDL required.
    """
    __tablename__ = 'chat_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tenant_id = db.Column(db.String(100), nullable=False, index=True)
    tenant_name = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='active', nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = db.relationship(
        'ChatMessage', backref='session', lazy=True,
        order_by='ChatMessage.created_at', cascade='all, delete-orphan',
    )


class ChatMessage(db.Model):
    """One turn in a ChatSession. `artifact_json` holds a render_artifact spec, if any."""
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_sessions.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' | 'assistant'
    content = db.Column(db.Text, nullable=False)
    artifact_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClientMemory(db.Model):
    """A durable fact about one tenant, remembered across Chat sessions/staff.

    Populated by the chat agent's `remember_fact` tool (see
    integrations/xero_mcp_client.py) so recurring context (vendor
    classifications, fiscal quirks, etc.) survives a 'New Chat'.
    """
    __tablename__ = 'client_memories'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(100), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(20), default='ai', nullable=False)  # 'ai' | 'manual'

    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CashFlowOutreachLog(db.Model):
    """A persisted record of one 'Send Outreach' click on the Cash Flow
    Accelerator. Sending itself is always a manual, human-clicked action
    (see routes/cash_flow_routes.py) — this table exists purely so later
    visits/scans can tell whether outreach already happened for a given
    opportunity, instead of that state vanishing with the page's JS on reload.
    """
    __tablename__ = 'cash_flow_outreach_log'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(100), nullable=False, index=True)
    opportunity_id = db.Column(db.String(100), nullable=False, index=True)
    opportunity_type = db.Column(db.String(30), nullable=False)
    contact_name = db.Column(db.String(200), nullable=True)
    sent_to = db.Column(db.String(200), nullable=True)

    sent_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    sent_by = db.relationship('User', foreign_keys=[sent_by_user_id])


class CashFlowOutcome(db.Model):
    """One resolved revenue opportunity, recorded automatically whenever a
    previously-detected opportunity id disappears from a new scan (manual or
    autonomous) — see helpers/cash_flow_insights.py:build_cash_flow_report.
    This is the 'measurable business outcome' evidence surfaced on the
    dashboard: what was flagged, whether outreach preceded it, and when it
    cleared.
    """
    __tablename__ = 'cash_flow_outcomes'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.String(100), nullable=False, index=True)
    opportunity_id = db.Column(db.String(100), nullable=False)
    opportunity_type = db.Column(db.String(30), nullable=False)
    contact_name = db.Column(db.String(200), nullable=True)
    impact_amount = db.Column(db.Float, default=0.0, nullable=False)
    outreach_sent = db.Column(db.Boolean, default=False, nullable=False)

    first_detected_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, default=datetime.utcnow)
