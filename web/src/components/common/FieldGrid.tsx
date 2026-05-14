import { valueText } from "../../api/format";

export function FieldGrid({
  record,
  fields
}: {
  record: Record<string, unknown>;
  fields: string[];
}) {
  return (
    <div className="field-grid">
      {fields.map((field) => (
        <div className="field-cell" key={field}>
          <span>{field}</span>
          <strong>{valueText(record[field])}</strong>
        </div>
      ))}
    </div>
  );
}
