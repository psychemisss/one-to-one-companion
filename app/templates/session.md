{% autoescape false %}# {{ t("session.md_title", name=e.name, date=s.date | fmt_date) }}

- {{ t("session.type") }}: {{ t("session.type." ~ s.session_type) }}
- {{ t("common.mood") }}: {{ s.mood or "—" }}
{% for key, _ in blocks %}
## {{ t("block." ~ key ~ ".title") }}

{{ notes.get(key) or "—" }}
{% endfor %}
{% if discussed %}
## {{ t("session.discussed_topics") }}

{% for a in discussed %}- {{ a.text }}
{% endfor %}{% endif %}
## {{ t("session.actions_created") }}

{% for a in created %}- [{{ "x" if a.status == "done" else " " }}] {{ a.text }} ({{ t("owner." ~ a.owner) }}{% if a.due_date %}, {{ a.due_date | fmt_date }}{% endif %})
{% else %}—
{% endfor %}
## {{ t("session.actions_closed") }}

{% for a in closed %}- {{ a.text }} ({{ t("status." ~ a.status) }})
{% else %}—
{% endfor %}
{% endautoescape %}
