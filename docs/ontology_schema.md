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

Construction-produced RCA views may add optional columns such as
`relation_family`, propagation flags, anchors, `source_trust`, `rca_score`, and
`rca_score_*` score components. These columns are profile-driven reasoning
metadata; they are not required in tracked seed KG files.
