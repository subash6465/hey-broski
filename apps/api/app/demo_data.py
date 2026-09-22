from .schemas import Source

DEMO_SOURCES = [
    Source(source_type="email", source_id="email-card-bill", account_label="Personal Gmail", title="Your card statement is ready", snippet="Payment of ₹12,450 is due on 25 September 2026.", timestamp="2026-09-20T08:30:00Z"),
    Source(source_type="email", source_id="email-manager-report", account_label="Work Outlook", title="Q3 project update", snippet="Could you send the revised project update by Wednesday?", timestamp="2026-09-21T10:15:00Z"),
    Source(source_type="document", source_id="doc-headphones-warranty", account_label="Document vault", title="Headphones warranty", snippet="Warranty coverage ends on 30 September 2026.", timestamp="2026-06-14T12:00:00Z"),
    Source(source_type="calendar", source_id="event-design-review", account_label="Work Calendar", title="Design review", snippet="23 September, 10:00–11:00; overlaps the client check-in.", timestamp="2026-09-23T10:00:00Z"),
    Source(source_type="calendar", source_id="event-client-checkin", account_label="Work Calendar", title="Client check-in", snippet="23 September, 10:30–11:15; overlaps the design review.", timestamp="2026-09-23T10:30:00Z"),
    Source(source_type="email", source_id="email-canva-renewal", account_label="Personal Gmail", title="Canva trial ending", snippet="Your trial renews on 27 September 2026 unless cancelled.", timestamp="2026-09-20T14:40:00Z"),
]
