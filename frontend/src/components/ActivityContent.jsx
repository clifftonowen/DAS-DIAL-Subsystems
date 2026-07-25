// ActivityContent.jsx — renders the LLM's activity text as a formatted document.
//
// The model returns lightweight Markdown ("**Objective:** …", "1. Clap the rhyme"),
// which read as literal asterisks when dropped into a <p>. This parses the subset
// the model actually emits — headings, bold/italic/code, ordered and unordered
// lists, paragraphs — rather than pulling in a Markdown dependency for six rules.
//
// Anything it does not recognise falls through as plain text, so a malformed
// response degrades to what we showed before instead of breaking the page.
//
// Props:
//   text {string} — raw completion from the backend

const HEADING = /^(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const ORDERED = /^\s*\d+[.)]\s+(.*)$/;

// **bold** | *italic* | `code` — captured so String.split keeps the delimiters.
const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g;

// Renders inline emphasis inside one line of text.
function inline(text) {
  return text.split(INLINE).filter(Boolean).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold text-brand-fg">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="rounded bg-brand-muted px-1 py-0.5 font-mono text-[0.9em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

// Groups raw lines into blocks: consecutive list items become one list, blank
// lines end the current paragraph.
function toBlocks(text) {
  const blocks = [];
  let list = null;      // { type: "ol" | "ul", items: [] }
  let paragraph = [];

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ type: "p", text: paragraph.join(" ") });
    paragraph = [];
  };
  const flushList = () => {
    if (list) blocks.push(list);
    list = null;
  };

  for (const raw of String(text ?? "").split("\n")) {
    const line = raw.trimEnd();

    if (!line.trim()) {                       // blank line — block boundary
      flushParagraph();
      flushList();
      continue;
    }

    const heading = line.match(HEADING);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: "h", level: heading[1].length, text: heading[2] });
      continue;
    }

    const ordered = line.match(ORDERED);
    if (ordered) {
      flushParagraph();
      if (list?.type !== "ol") { flushList(); list = { type: "ol", items: [] }; }
      list.items.push(ordered[1]);
      continue;
    }

    // Checked after ORDERED so "1. x" never matches, and requires the "- " space
    // so a line of emphasis like "*note*" is not mistaken for a bullet.
    const bullet = line.match(BULLET);
    if (bullet) {
      flushParagraph();
      if (list?.type !== "ul") { flushList(); list = { type: "ul", items: [] }; }
      list.items.push(bullet[1]);
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  return blocks;
}

export default function ActivityContent({ text }) {
  const blocks = toBlocks(text);

  return (
    <div className="font-reading text-[15px] leading-[1.65] text-brand-fg">
      {blocks.map((block, i) => {
        if (block.type === "h") {
          // The model's own h1 is the activity title; render every level at a
          // size that sits under the card heading rather than competing with it.
          const size = block.level <= 2 ? "text-base" : "text-[15px]";
          return (
            <p key={i} className={`${size} mb-1.5 mt-5 font-display font-semibold text-brand-fg first:mt-0`}>
              {inline(block.text)}
            </p>
          );
        }

        if (block.type === "p") {
          return <p key={i} className="mb-3 last:mb-0">{inline(block.text)}</p>;
        }

        const List = block.type === "ol" ? "ol" : "ul";
        return (
          <List
            key={i}
            className={`mb-3 space-y-1.5 pl-5 last:mb-0 ${
              block.type === "ol" ? "list-decimal" : "list-disc"
            } marker:text-brand-fg-muted`}
          >
            {block.items.map((item, j) => (
              <li key={j} className="pl-1">{inline(item)}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
