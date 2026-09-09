# Input contract

UTF-8 JSON object, version 1. All content is plain text, including Markdown source; HTML is displayed literally. The generator rejects unknown fields to expose misspellings.

```json
{
  "version": 1,
  "id": "design-feedback-2026-09-08-01",
  "title": "Reply to the design proposal",
  "language": "en",
  "source": "The complete original Agent response, unchanged.",
  "items": [
    {
      "id": "navigation",
      "subject": "Navigation alternatives",
      "question": "Which direction would you like to explore?",
      "context": "The proposal offers a sidebar or tabs.",
      "kind": "single",
      "options": ["Sidebar", "Tabs", "Explore another direction"]
    },
    {
      "id": "accessibility",
      "subject": "Accessibility review",
      "question": "What should be checked next?",
      "context": "The proposal does not include keyboard testing.",
      "kind": "text"
    }
  ]
}
```

`language` is `en` or `zh` and controls interface labels, not the content. Every field shown is required except `options`, which is required for `single` and `multiple` and prohibited for `text`. Item IDs must be unique. IDs contain ASCII letters, digits, hyphens, or underscores. `items` must be nonempty. Choice labels must be nonempty and unique. Every item includes an optional free-text field regardless of kind. There is no default-answer field.

Generated Markdown contains the packet title and ID, overall feedback, each item's subject, question, context, selected choice labels and answer or explicit unanswered state. Unselected choices are omitted; do not answer using bare option numbers. The original source remains available in the HTML; it is not duplicated in full in the exported reply. Context must therefore be sufficient to distinguish each matter independently.
