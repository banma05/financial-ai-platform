import { useEffect, useCallback, useRef, useState, type DragEvent, type ChangeEvent } from 'react';
import { api } from '@/api/client';
import { useDocumentStore, type DocInfo, type ChatMessage } from '@/stores/document';

/**
 * 文档问答页面 — PDF 拖拽上传 + 文档列表 + RAG 智能问答
 * V8.3: 全面美化 — brand 色系、悬浮卡片、现代聊天气泡
 */
export default function DocumentUpload() {
  const {
    documents, isUploading, uploadError, chatHistory, isChatting, chatError,
    setDocuments, addDocument, setIsUploading, setUploadError,
    addMessage, setIsChatting, setChatError,
  } = useDocumentStore();

  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // 加载文档列表
  useEffect(() => {
    if (documents.length > 0) return;
    let cancelled = false;
    api.get<{ documents: DocInfo[] }>('/rag/documents')
      .then((resp) => { if (!cancelled) setDocuments(resp.documents || []); })
      .catch((err) => { if (!cancelled) setUploadError(err instanceof Error ? err.message : '加载文档列表失败'); });
    return () => { cancelled = true; };
  }, [documents.length, setDocuments, setUploadError]);

  // 自动滚动到底部
  useEffect(() => {
    chatEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [chatHistory]);

  // 文件上传
  const handleFile = useCallback(async (file: File) => {
    if (file.type !== 'application/pdf'
        && file.type !== 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        && file.type !== 'text/plain' && file.type !== 'text/markdown'
        && !file.name.endsWith('.docx') && !file.name.endsWith('.doc')
        && !file.name.endsWith('.md') && !file.name.endsWith('.txt')) {
      setUploadError('仅支持 PDF、Word (.docx/.doc)、Markdown、TXT 文件');
      return;
    }
    setIsUploading(true);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await api.post<{ filename: string; chunk_count: number; file_size: number; message: string }>(
        '/rag/upload', formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      addDocument({
        filename: resp.filename,
        chunk_count: resp.chunk_count,
        page_count: 0,
        file_size: resp.file_size,
        upload_time: new Date().toLocaleString(),
      });
      if (!selectedDoc) setSelectedDoc(resp.filename);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : '上传失败');
    } finally {
      setIsUploading(false);
    }
  }, [setIsUploading, setUploadError, addDocument, selectedDoc]);

  // 拖拽事件
  const onDragOver = (e: DragEvent) => { e.preventDefault(); setIsDragOver(true); };
  const onDragLeave = () => setIsDragOver(false);
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  // 文件选择
  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  // 发送问题
  const handleSend = useCallback(async () => {
    const q = question.trim();
    if (!q || isChatting) return;

    const userMsg: ChatMessage = { role: 'user', content: q };
    addMessage(userMsg);
    setQuestion('');
    setIsChatting(true);
    setChatError(null);

    try {
      const resp = await api.post<{ answer: string; sources: ChatMessage['sources']; processing_time: number }>('/rag/chat', {
        query: q, top_k: 5, session_id: `rag-${Date.now()}`,
      });
      addMessage({ role: 'assistant', content: resp.answer, sources: resp.sources });
    } catch (err) {
      setChatError(err instanceof Error ? err.message : '问答请求失败');
    } finally {
      setIsChatting(false);
    }
  }, [question, isChatting, addMessage, setIsChatting, setChatError]);

  const canSend = question.trim().length > 0 && !isChatting;

  return (
    <div className="max-w-5xl mx-auto flex gap-6 h-[calc(100vh-6rem)] animate-fade-in-up">
      {/* ── 左侧：上传 + 文档列表 ── */}
      <div className="w-80 flex-shrink-0 flex flex-col gap-4">
        <div className="mb-1">
          <h1 className="text-2xl font-bold text-gray-900">文档问答</h1>
          <p className="mt-1 text-sm text-gray-500">上传年报 PDF，基于原文精准问答</p>
        </div>

        {/* 拖拽上传区 */}
        <div
          role="button"
          tabIndex={0}
          aria-label="上传 PDF 文件"
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click(); } }}
          className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all duration-200 ${
            isDragOver
              ? 'border-brand-500 bg-brand-50 scale-[1.02]'
              : 'border-gray-200 bg-gray-50/50 hover:border-brand-300 hover:bg-brand-50/30'
          }`}
        >
          <div className="text-3xl mb-2">{isUploading ? '⏳' : '📄'}</div>
          <p className="text-sm text-gray-600 font-medium">
            {isUploading ? '正在上传解析...' : isDragOver ? '松开以上传文件' : '拖拽文件到此处上传'}
          </p>
          <p className="text-xs text-gray-400 mt-1">或点击选择文件</p>
          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            💡 支持 <strong>年报 PDF</strong>、<strong>研报 .docx</strong>、<strong>招股说明书</strong>
          </p>
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.md,.txt" onChange={onFileChange} className="hidden" />
        </div>

        {uploadError && (
          <div className="p-2.5 bg-danger-50 border border-red-200 rounded-lg text-xs text-danger-700">{uploadError}</div>
        )}

        {/* 文档列表 */}
        <div className="flex-1 overflow-auto">
          <h2 className="text-sm font-semibold text-gray-600 mb-2.5 flex items-center gap-2">
            已上传文档
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-brand-100 text-brand-700 text-xs font-bold">{documents.length}</span>
          </h2>
          {documents.length === 0 ? (
            <p className="text-xs text-gray-400">暂无文档，上传一份 PDF 开始分析</p>
          ) : (
            <ul className="space-y-2">
              {documents.map((doc) => (
                <li
                  key={doc.filename}
                  onClick={() => setSelectedDoc(doc.filename)}
                  className={`p-3 rounded-lg text-sm cursor-pointer transition-all duration-200 ${
                    selectedDoc === doc.filename
                      ? 'bg-brand-50 border border-brand-200 shadow-sm'
                      : 'bg-white border border-gray-200 hover:border-gray-300 hover:shadow-sm'
                  }`}
                >
                  <div className="font-medium text-gray-800 truncate">{doc.filename}</div>
                  <div className="text-xs text-gray-400 mt-1 flex items-center gap-2">
                    <span>{doc.chunk_count} 文本块</span>
                    <span className="w-1 h-1 rounded-full bg-gray-300" />
                    <span>{doc.upload_time}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* ── 右侧：RAG 问答 ── */}
      <div className="flex-1 flex flex-col card overflow-hidden">
        {/* 顶栏 */}
        <div className="px-5 py-3.5 border-b border-border-default bg-gray-50/50">
          <h2 className="font-semibold text-sm text-gray-800">RAG 智能问答</h2>
          {selectedDoc && (
            <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
              基于文档：{selectedDoc}
            </p>
          )}
        </div>

        {/* 聊天记录 */}
        <div className="flex-1 overflow-auto p-4 space-y-4 bg-surface-muted/30">
          {chatHistory.length === 0 && (
            <div className="text-center mt-16">
              <div className="text-4xl mb-3">💬</div>
              <p className="text-sm text-gray-400">选择一份文档，在下方输入问题开始分析</p>
              <p className="text-xs text-gray-400 mt-1">AI 将在文档原文中检索最相关的段落来回答</p>
            </div>
          )}
          {chatHistory.map((msg, i) => (
            <div key={`${msg.role}-${i}-${msg.content.slice(0, 20)}`}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in`}>
              <div className={`max-w-[80%] rounded-2xl p-3.5 text-sm ${
                msg.role === 'user'
                  ? 'bg-gradient-to-br from-brand-600 to-brand-500 text-white shadow-sm'
                  : 'bg-white text-gray-800 border border-border-default shadow-sm'
              }`}>
                <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-200/50">
                    <p className="text-xs font-semibold text-gray-500 mb-1.5">📎 来源引用</p>
                    {msg.sources.slice(0, 3).map((src, j) => (
                      <div key={j} className="text-xs text-gray-500 mt-1.5 bg-gray-50 rounded-lg p-2">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-gray-700">{src.source}</span>
                          <span className="text-gray-300">·</span>
                          <span>第{src.page}页</span>
                          <span className="text-gray-300">·</span>
                          <span className="text-green-600 font-medium">相关度 {(src.score * 100).toFixed(0)}%</span>
                        </div>
                        <p className="text-gray-400 line-clamp-2 mt-0.5">{src.content}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {isChatting && (
            <div className="flex items-center gap-2 text-sm text-gray-400 px-1">
              <span className="spinner w-4 h-4 border-2 border-brand-300 border-t-brand-600 rounded-full" />
              正在检索分析...
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {chatError && (
          <div className="px-4 py-2 bg-danger-50 text-xs text-danger-700 border-t border-red-200">{chatError}</div>
        )}

        {/* 输入区 */}
        <div className="p-4 border-t border-border-default bg-white flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { handleSend().catch(() => {}); } }}
            placeholder="输入问题，例如：茅台2024年营收增长了多少？"
            aria-label="输入分析问题"
            className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm
              placeholder:text-gray-400
              focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100
              transition-all duration-200"
          />
          <button
            onClick={handleSend}
            disabled={!canSend}
            className={`px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 ${
              canSend
                ? 'bg-gradient-to-r from-brand-600 to-brand-500 text-white shadow-sm hover:shadow-md hover:-translate-y-0.5 active:translate-y-0'
                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
            }`}
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
