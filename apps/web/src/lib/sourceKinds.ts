// Only a PDF can be embedded natively in the browser — .pptx and transcripts fall back to
// extracted/transcribed text. Shared by SourcePreviewPanel (the full-document preview) and
// SourcePassage/ReviewSourcePassage (the "view original page" button on an anchor quote).
export const EMBEDDABLE_KINDS = new Set(['lecture_pdf', 'paper'])
