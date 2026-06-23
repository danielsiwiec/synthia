_MAX_PROJECT_CONTEXT_DOC = 6000


def build_project_context(project: dict, max_doc: int = _MAX_PROJECT_CONTEXT_DOC) -> str:
    document = (project.get("document") or "").strip()
    if len(document) > max_doc:
        document = document[:max_doc] + "\n…(document truncated)"
    return (
        f'[The user is currently working in the context of the project "{project["name"]}" '
        f"(status: {project['status']}, project id: {project['id']}). Next step: "
        f"{project.get('next_step') or '(none set)'}. Treat this message — and following ones — as "
        f"being about this project. Project edits are yours to make: if they ask to update, rename, "
        f"close, replace, or add to it, do it yourself with your project tools and that project id, "
        f"and keep its next step current — never delegate a project edit. Do NOT give this project "
        f"id to the task agent; it has no project tools and would mistake the id for an external "
        f"resource (e.g. a Notion page). If the change needs research or other information you must "
        f"gather first, delegate ONLY that gathering to the task agent (no project id); you will be "
        f"handed its result when it finishes, and then you write that result into the project "
        f"yourself with update_project. The project's current document is:\n---\n"
        f"{document or '(empty)'}\n---]"
    )
