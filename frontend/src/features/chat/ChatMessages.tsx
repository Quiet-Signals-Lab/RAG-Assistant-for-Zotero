import React from "react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "../../types/domain";
import { Spinner } from "../../components/ui/Spinner";
import { useResponseSelection } from "../../contexts/ResponseSelectionContext";
import ReasoningSection from "../../components/ui/ReasoningSection";
import { useSettings } from "../../contexts/SettingsContext";
import { normaliseMarkdown } from "./markdown";

interface Props {
  messages: ChatMessage[];
  loading: boolean;
}

function formatMessageWithCitations(content: string | undefined): React.ReactNode {
  // Handle undefined or empty content
  if (!content) {
    return <span>No response available</span>;
  }
  
  const processedContent = normaliseMarkdown(content);
  
  // Custom renderer that handles citations inline without breaking flow
  const renderContentWithCitations = (text: string) => {
    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    
    // Match citation patterns [1], [2][3], etc.
    const citationRegex = /\[\d+\](?:\[\d+\])*/g;
    let match: RegExpExecArray | null;
    
    while ((match = citationRegex.exec(text)) !== null) {
      const currentMatch = match; // Create a const reference for TypeScript
      
      // Add text before citation
      if (currentMatch.index > lastIndex) {
        parts.push(text.substring(lastIndex, currentMatch.index));
      }
      
      // Add citations as superscripts
      const citations = currentMatch[0].match(/\[\d+\]/g) || [];
      citations.forEach((cite, idx) => {
        parts.push(
          <sup key={`cite-${currentMatch.index}-${idx}`} className="citation-ref">
            {cite}
          </sup>
        );
      });
      
      lastIndex = currentMatch.index + currentMatch[0].length;
    }
    
    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }
    
    return parts;
  };
  
  return (
    <ReactMarkdown
      components={{
        // Paragraph handling - render inline content properly
        p: ({node, children, ...props}) => {
          // Process children to handle citations
          const processedChildren = React.Children.map(children, (child) => {
            if (typeof child === 'string') {
              return renderContentWithCitations(child);
            }
            return child;
          });
          return <p {...props}>{processedChildren}</p>;
        },
        // Headings with proper spacing
        h1: ({node, children, ...props}) => {
          const processedChildren = React.Children.map(children, (child) => {
            if (typeof child === 'string') {
              return renderContentWithCitations(child);
            }
            return child;
          });
          return <h1 {...props}>{processedChildren}</h1>;
        },
        h2: ({node, children, ...props}) => {
          const processedChildren = React.Children.map(children, (child) => {
            if (typeof child === 'string') {
              return renderContentWithCitations(child);
            }
            return child;
          });
          return <h2 {...props}>{processedChildren}</h2>;
        },
        h3: ({node, children, ...props}) => {
          const processedChildren = React.Children.map(children, (child) => {
            if (typeof child === 'string') {
              return renderContentWithCitations(child);
            }
            return child;
          });
          return <h3 {...props}>{processedChildren}</h3>;
        },
        // Strong (bold) with citation support
        strong: ({node, children, ...props}) => {
          const processedChildren = React.Children.map(children, (child) => {
            if (typeof child === 'string') {
              return renderContentWithCitations(child);
            }
            return child;
          });
          return <strong {...props}>{processedChildren}</strong>;
        },
        em: ({node, ...props}) => <em {...props} />,
        code: ({node, ...props}) => <code {...props} />,
        pre: ({node, ...props}) => <pre {...props} />,
        ul: ({node, ...props}) => <ul {...props} />,
        ol: ({node, ...props}) => <ol {...props} />,
        li: ({node, children, ...props}) => {
          const processedChildren = React.Children.map(children, (child) => {
            if (typeof child === 'string') {
              return renderContentWithCitations(child);
            }
            return child;
          });
          return <li {...props}>{processedChildren}</li>;
        },
        blockquote: ({node, ...props}) => <blockquote {...props} />,
        a: ({node, ...props}) => <a target="_blank" rel="noopener noreferrer" {...props} />,
      }}
    >
      {processedContent}
    </ReactMarkdown>
  );
}

const ChatMessages: React.FC<Props> = ({ messages, loading }) => {
  const messagesEndRef = React.useRef<HTMLDivElement>(null);
  const [copiedId, setCopiedId] = React.useState<string | null>(null);
  const { selectedResponseId, setSelectedResponseId } = useResponseSelection();
  const { updateSettings } = useSettings();

  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleCopy = async (content: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(messageId);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  return (
    <div className="chat-view__messages">
      <div className="message-list">
        {messages.length === 0 && !loading && (
          <div className="message-list__empty">
            <div className="desk-intro">
              <h2>Legacy chat.</h2>
              <p>
                Ask a question and a model writes an answer from passages in your library, with numbered citations.
                Check every claim against the evidence and sources beside it: the answer is the model's, not your sources'.
              </p>
              <p>Search returns the sources themselves, ranked, with no model in between.</p>
              <button type="button" className="btn" onClick={() => updateSettings({ interfaceMode: "desk" })}>
                Switch to search
              </button>
            </div>
          </div>
        )}
        {messages.map((m) => {
          const isAnswer = m.role === "assistant";
          const selected = isAnswer && selectedResponseId === m.id;
          return (
            <article
              key={m.id}
              className={["message", isAnswer ? "message--assistant" : "message--user", selected ? "message--selected" : ""].filter(Boolean).join(" ")}
              data-response-id={isAnswer ? m.id : undefined}
              onClick={isAnswer ? () => setSelectedResponseId(m.id) : undefined}
            >
              <div className="message__role">
                {isAnswer ? (
                  <>
                    <span>Answer</span>
                    <span className="message__note"> · written by the model</span>
                  </>
                ) : (
                  "Your question"
                )}
              </div>
              <div className="message__body">{formatMessageWithCitations(m.content)}</div>
              {isAnswer && m.reasoning && <ReasoningSection reasoning={m.reasoning} messageId={m.id} />}
              {isAnswer && (
                <div className="message__actions">
                  <button
                    type="button"
                    className="btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCopy(m.content, m.id);
                    }}
                  >
                    {copiedId === m.id ? "Copied" : "Copy answer"}
                  </button>
                  {!selected && (
                    <button type="button" className="btn" onClick={() => setSelectedResponseId(m.id)}>
                      Show its evidence
                    </button>
                  )}
                </div>
              )}
            </article>
          );
        })}
        {loading && (
          <article className="message message--assistant" aria-busy="true">
            <div className="message__role">Answer</div>
            <div className="message__body message__body--working">
              <Spinner size="sm" />
              <span>Reading your library and writing an answer…</span>
            </div>
          </article>
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
};

export default ChatMessages;
