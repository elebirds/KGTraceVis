# Ontology Schema

Tracked KG nodes use:

```csv
id,name,label,scenario,aliases,description
```

Tracked KG edges use:

```csv
head,relation,tail,scenario,source,evidence,confidence,weight,review_status,feedback_count,accepted_count,rejected_count
```

Every non-example edge must be source-constrained and reviewable.
