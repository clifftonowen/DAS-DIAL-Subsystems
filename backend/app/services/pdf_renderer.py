
"""renderPDF — turns a learning activity into PDF bytes.
 
Uses PyMuPDF's Story engine. ActivityContent.jsx is converted to a small HTML document 
"""
import html
import io
import re
import fitz
 
class PdfRenderError(Exception):
    "This activity could not be rendered to PDF."
 
# Markdown subset the model actually emits, mirroring ActivityContent.jsx.
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^\s*[-*\•]\s+(.*)$")
ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
 
PAGE_CSS = """
body   { font-family: serif; }
h1     { font-family: sans-serif; font-size: 17px; margin-bottom: 2px; }
h2, h3 { font-family: sans-serif; font-size: 12.5px; margin-top: 12px; margin-bottom: 2px; }
p      { font-size: 10.5px; line-height: 1.45; margin-top: 0; margin-bottom: 7px; }
li     { font-size: 10.5px; line-height: 1.45; margin-bottom: 3px; }
.meta  { font-size: 8.5px; color: #666666; margin-bottom: 14px; }
.foot  { font-size: 8px; color: #888888; margin-top: 18px; }
"""
 
 
class ActivityPdfRenderer:
    def render(self, activity: dict) -> bytes:
        """Render one learning_activities row to PDF bytes."""
        try:
            document = self._build_html(activity)
            return self._to_pdf(document)
        except PdfRenderError:
            raise
        except Exception as exc:  
            raise PdfRenderError(f"Could not render activity as PDF: {exc}") from exc
 
    def _build_html(self, activity: dict) -> str:
        activity = activity or {}
        content = activity.get("content") or {}
        body_text = content.get("text") or ""
        if not body_text.strip():
            raise PdfRenderError("Activity has no content to export")
 
        objective = activity.get("literacy_objective") or "Learning Activity"
        meta_bits = [
            f"Level: {activity['level']}" if activity.get("level") else None,
            f"Status: {activity['status']}" if activity.get("status") else None,
            f"Generated: {str(activity.get('created_at', ''))[:10]}"
            if activity.get("created_at") else None,
        ]
        meta = " &#183; ".join(b for b in meta_bits if b)
 
        grounded = activity.get("grounded_on") or []
        sources = ""
        if grounded:
            items = "".join(f"<li>{html.escape(str(g))}</li>" for g in grounded)
            sources = f"<h3>Curriculum sources</h3><ul>{items}</ul>"
 
        return (
            "<html><body>"
            f"<h1>{html.escape(str(objective))}</h1>"
            f'<p class="meta">{meta}</p>'
            f"{self._markdown_to_html(body_text)}"
            f"{sources}"
            '<p class="foot">By DAS D.I.A.L</p>'
            "</body></html>"
        )
 
    def _markdown_to_html(self, text: str) -> str:
        out: list[str] = []
        open_list: str | None = None
 
        def close_list() -> None:
            nonlocal open_list
            if open_list:
                out.append(f"</{open_list}>")
                open_list = None
 
        def open_as(tag: str) -> None:
            nonlocal open_list
            if open_list != tag:
                close_list()
                out.append(f"<{tag}>")
                open_list = tag
 
        for raw in str(text).split("\n"):
            line = raw.strip()
            if not line:
                close_list()
                continue
 
            heading = HEADING.match(line)
            if heading:
                close_list()
                level = min(len(heading.group(1)) + 1, 3) 
                out.append(f"<h{level}>{self._inline(heading.group(2))}</h{level}>")
                continue
 
            ordered = ORDERED.match(line)
            if ordered:
                open_as("ol")
                out.append(f"<li>{self._inline(ordered.group(1))}</li>")
                continue
 
            bullet = BULLET.match(line)
            if bullet:
                open_as("ul")
                out.append(f"<li>{self._inline(bullet.group(1))}</li>")
                continue
 
            close_list()
            out.append(f"<p>{self._inline(line)}</p>")
 
        close_list()
        return "".join(out)
 
    def _inline(self, text: str) -> str:
        return BOLD.sub(r"<b>\1</b>", html.escape(text))
 

    def _to_pdf(self, document_html: str) -> bytes:
        buffer = io.BytesIO()
        writer = fitz.DocumentWriter(buffer)
        story = fitz.Story(html=document_html, user_css=PAGE_CSS)
 
        mediabox = fitz.paper_rect("a4")
        frame = mediabox + (56, 56, -56, -56) 
 
        more = 1
        pages = 0
        while more:
            device = writer.begin_page(mediabox)
            more, _ = story.place(frame)
            story.draw(device)
            writer.end_page()
            pages += 1

        writer.close()
        return buffer.getvalue()
 

