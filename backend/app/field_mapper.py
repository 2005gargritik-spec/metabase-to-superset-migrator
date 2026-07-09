"""Resolve MBQL field references using the metadata of the current table."""


class FieldMapper:
    def __init__(self, metadata):
        self.metadata = metadata or {}
        self.fields = self.metadata.get("fields", [])
        self.id_to_field = {}
        self.name_to_field = {}
        for field in self.fields:
            field_id = field.get("id")
            if field_id is not None:
                try:
                    self.id_to_field[field_id] = field
                except TypeError:
                    pass
            if field.get("name"):
                self.name_to_field[field["name"]] = field

    def field(self, reference):
        """Accept legacy field IDs and modern [\"field\", id, options] refs."""
        if isinstance(reference, dict):
            for key in ("id", "field_id", "name"):
                value = reference.get(key)
                if value is not None:
                    return self.field(value)
            return None
        if isinstance(reference, (list, tuple)):
            if reference and reference[0] in ("field", "field-id"):
                if len(reference) > 2 and isinstance(reference[1], dict):
                    reference = reference[2]
                else:
                    reference = reference[1]
            elif len(reference) > 2 and isinstance(reference[2], int):
                reference = reference[2]
        if isinstance(reference, str) and reference in self.name_to_field:
            return self.name_to_field[reference]
        try:
            return self.id_to_field.get(reference)
        except TypeError:
            return None

    def get_name(self, reference):
        field = self.field(reference)
        if not field:
            raise ValueError(f"Metabase field reference {reference!r} is absent from table metadata")
        return field["name"]

    def is_temporal(self, reference):
        field = self.field(reference) or {}
        value = " ".join(str(field.get(k, "")) for k in ("base_type", "effective_type", "semantic_type", "special_type"))
        return any(token in value.lower() for token in ("date", "time"))

    def all_names(self):
        return [f["name"] for f in self.fields if f.get("name")]
