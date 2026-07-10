import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/** 共享 Markdown 渲染组件（预设分析 & 报告展示 共用） */
export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ ...props }) => <h1 className="text-2xl font-bold mt-6 mb-4 text-gray-900" {...props} />,
        h2: ({ ...props }) => <h2 className="text-xl font-semibold mt-5 mb-3 text-gray-800" {...props} />,
        h3: ({ ...props }) => <h3 className="text-lg font-medium mt-4 mb-2 text-gray-700" {...props} />,
        p: ({ ...props }) => <p className="text-sm text-gray-700 leading-relaxed mb-3" {...props} />,
        strong: ({ ...props }) => <strong className="font-semibold text-gray-900" {...props} />,
        ul: ({ ...props }) => <ul className="list-disc pl-5 mb-3 space-y-1" {...props} />,
        ol: ({ ...props }) => <ol className="list-decimal pl-5 mb-3 space-y-1" {...props} />,
        li: ({ ...props }) => <li className="text-sm text-gray-700" {...props} />,
        table: ({ ...props }) => (
          <div className="overflow-auto mb-4 border rounded-lg">
            <table className="min-w-full text-sm" {...props} />
          </div>
        ),
        thead: ({ ...props }) => <thead className="bg-gray-50" {...props} />,
        th: ({ ...props }) => <th className="px-3 py-2 text-left font-medium text-gray-600 border-b" {...props} />,
        td: ({ ...props }) => <td className="px-3 py-2 text-gray-700 border-b border-gray-100" {...props} />,
        code: ({ ...props }) => <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs text-pink-600" {...props} />,
        blockquote: ({ ...props }) => <blockquote className="border-l-4 border-blue-300 pl-4 italic text-gray-600 my-3" {...props} />,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
