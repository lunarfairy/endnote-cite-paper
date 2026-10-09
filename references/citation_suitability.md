# Citation Suitability Rules

## Sentence-Level Fit

- Match references to the exact claim in the target sentence, not just the general topic.
- Prefer 1-3 precise references over 4-5 broad references.
- Do not cite a reference merely because it contains similar keywords.
- If a sentence contains multiple claims, split the citation needs into clause-level anchors or cite sources covering each claim. Split the manuscript sentence itself only when the user has authorized that prose change; otherwise record a recommendation.
- If no source precisely supports the sentence, mark the citation need as unresolved instead of forcing a weak match.

## Avoid Weak Matches

- Do not use broad social-ecological systems reviews to support a specific mathematical modeling choice unless the review actually discusses that choice.
- Do not use global fisheries papers to support claims about tropical forests or extractor heterogeneity unless the paper directly addresses those dimensions.
- Do not cite external literature for the manuscript's own figure-specific findings, such as "Figure 3 demonstrates..." or "our results reveal...", unless the citation supports the method or background rather than the new result itself.
- Do not cite broad telecoupling/metacoupling literature as if it directly proves a manuscript-specific coined mechanism. Use an existing background anchor. Separating the author's concept into new prose is a recommendation unless that edit is already authorized.
- Do not use decision-under-risk or bounded-rationality classics as direct support for resource-scarcity feedback unless the sentence is framed as a modeling foundation or operationalization.
- Do not use network cooperation literature to support a specific simulation update algorithm unless the source discusses that algorithm. It can support the broader network evolutionary-game framework.
- Do not use general cooperation/punishment literature to support environment-specific claims such as scarcity-driven cooperation or abundance-driven defection unless the paper discusses environmental contingency or resource scarcity.
- Do not cite regime-shift or planetary-boundary literature as support for logistic growth modeling. Use sources on renewable resource dynamics, logistic growth, or bioeconomic resource models.
- For perception hysteresis, delayed recognition, or shifting baseline claims, include direct references on shifting baselines, environmental perception, memory, or delayed response.

## Review Gate

Before delivery, run a separate suitability pass over citation needs, insertion mapping, and the verified reference table. These can remain internal; do not require a collaborator package when the user only needs Word.

Fail the run when:

- Any insertion point exceeds the selected maximum (default 5; use a different limit only when explicitly requested).
- The DOCX EndNote field itself exceeds that maximum of embedded `<Cite>` records, even if the mapping table looks clean. Pass the same limit to mapping and field validation.
- Any `reference_id` in the mapping is missing from the candidate table.
- A citation group is only broadly related to the target sentence.
- A model-specific claim is cited with background literature that does not directly support it.

Record problematic `citation_id` values in the test report and revise the mapping before final EndNote formatting.
