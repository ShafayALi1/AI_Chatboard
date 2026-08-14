// A deliberately small renderer -- just enough formatting for support
// answers (paragraphs, fenced code, inline code, bold, simple lists)
// without pulling in a full markdown dependency.

import type { ReactNode } from "react";

function renderInline(text: string, keyPrefix: string) {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];

    if (token.startsWith("**")) {
      nodes.push(
        <strong key={`${keyPrefix}-b-${index}`}>{token.slice(2, -2)}</strong>
      );
    } else {
      nodes.push(
        <code key={`${keyPrefix}-c-${index}`} className="inline-code">
          {token.slice(1, -1)}
        </code>
      );
    }

    lastIndex = match.index + token.length;
    index += 1;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

export function renderContent(content: string) {
  const segments = content.split(/```/);

  return segments.map((segment, segmentIndex) => {
    const isCodeBlock = segmentIndex % 2 === 1;

    if (isCodeBlock) {
      const lines = segment.split("\n");
      const firstLineIsLang = lines.length > 1 && /^[a-zA-Z0-9_+-]*$/.test(lines[0].trim());
      const code = firstLineIsLang ? lines.slice(1).join("\n") : segment;

      return (
        <pre key={`code-${segmentIndex}`} className="code-block">
          <code>{code.trim()}</code>
        </pre>
      );
    }

    const paragraphs = segment.split(/\n{2,}/).filter((p) => p.trim() !== "");

    if (paragraphs.length === 0) {
      return null;
    }

    return paragraphs.map((paragraph, paragraphIndex) => {
      const lines = paragraph.split("\n");
      const isList = lines.every((line) => /^\s*[-*]\s+/.test(line));

      if (isList) {
        return (
          <ul key={`list-${segmentIndex}-${paragraphIndex}`} className="message-list">
            {lines.map((line, lineIndex) => (
              <li key={lineIndex}>
                {renderInline(line.replace(/^\s*[-*]\s+/, ""), `${segmentIndex}-${paragraphIndex}-${lineIndex}`)}
              </li>
            ))}
          </ul>
        );
      }

      return (
        <p key={`p-${segmentIndex}-${paragraphIndex}`}>
          {lines.map((line, lineIndex) => (
            <span key={lineIndex}>
              {renderInline(line, `${segmentIndex}-${paragraphIndex}-${lineIndex}`)}
              {lineIndex < lines.length - 1 && <br />}
            </span>
          ))}
        </p>
      );
    });
  });
}
