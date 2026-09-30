from jinja2 import Template


class CoverLetterService:
    def render(self, template: str, context: dict[str, str | float]) -> str:
        """Render a user-controlled draft. Never send it without explicit approval."""
        # TODO: restrict template features / sandbox if templates can be edited by untrusted users.
        return Template(template).render(**context)


class ApplicationService:
    # TODO: create draft, state transitions, event log, enqueue after approve.
    pass
