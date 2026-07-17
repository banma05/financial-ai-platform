import { useEffect, useCallback, useRef, useState, type DragEvent, type ChangeEvent } from 'react';
import { api } from '@/api/client';
import { useDocumentStore, type DocInfo, type ChatMessage } from '@/stores/document';

/**
 * 文档上传页面 — PDF 拖拽上传 + 文档列表 + RAG 问答
 */
export default function DocumentUpload() {
  const {
    documents,
    isUploading,
    uploadError,
    chatHistory,
    isChatting,
    chatError,
    setDocuments,
    addDocument,
    setIsUploading,
    setUploadError,
    addMessage,
    setIsChatting,
    setChatError,
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
      .then((resp) => {
        if (cancelled) return;
        setDocuments(resp.documents || []);
      })
      .catch((err) => {
        if (!cancelled) setUploadError(err instanceof Error ? err.message : '加载文档列表失败');
      });
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
        && file.type !== 'text/plain'
        && file.type !== 'text/markdown'
        && !file.name.endsWith('.docx')
        && !file.name.endsWith('.doc')
        && !file.name.endsWith('.md')
        && !file.name.endsWith('.txt')) {
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
        query: q,
        top_k: 5,
        session_id: `rag-${Date.now()}`,
      });
      addMessage({
        role: 'assistant',
        content: resp.answer,
        sources: resp.sources,
      });
    } catch (err) {
      setChatError(err instanceof Error ? err.message : '问答请求失败');
    } finally {
      setIsChatting(false);
    }
  }, [question, isChatting, addMessage, setIsChatting, setChatError]);

  const canSend = question.trim().length > 0 && !isChatting;

  return (
    <div className="max-w-5xl mx-auto flex gap-6 h-[calc(100vh-6rem)]">
      {/* 左侧：上传 + 文档列表 */}
      <div className="w-80 flex-shrink-0 flex flex-col gap-4">
        <h1 className="text-2xl font-bold">文档上传</h1>

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
          className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
            isDragOver
              ? 'border-blue-500 bg-blue-50'
              : 'border-gray-300 bg-gray-50 hover:border-blue-400'
          }`}
        >
          <div className="text-3xl mb-2">📄</div>
          <p className="text-sm text-gray-600">
            {isUploading ? '上传中...' : isDragOver ? '松开以上传' : '拖拽 PDF/Word 文件到此处上传'}
          </p>
          <p className="text-xs text-gray-400 mt-1">或点击选择文件</p>
          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            💡 建议上传<strong>年报 PDF</strong>、<strong>券商研报 .docx</strong>、<strong>招股说明书</strong>，以获得更全面的财务分析
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.md,.txt"
            onChange={onFileChange}
            className="hidden"
          />
        </div>

        {uploadError && (
          <div className="p-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">{uploadError}</div>
        )}

        {/* 文档列表 */}
        <div className="flex-1 overflow-auto">
          <h2 className="text-sm font-medium text-gray-600 mb-2">已上传文档 ({documents.length})</h2>
          {documents.length === 0 ? (
            <p className="text-xs text-gray-400">暂无文档，上传一份 PDF 开始分析</p>
          ) : (
            <ul className="space-y-2">
              {documents.map((doc) => (
                <li
                  key={doc.filename}
                  onClick={() => setSelectedDoc(doc.filename)}
                  className={`p-3 rounded-lg text-sm cursor-pointer transition-colors ${
                    selectedDoc === doc.filename
                      ? 'bg-blue-50 border border-blue-200'
                      : 'bg-white border border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="font-medium truncate">{doc.filename}</div>
                  <div className="text-xs text-gray-400 mt-1">
                    {doc.chunk_count} chunks · {doc.upload_time}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* 右侧：RAG 问答 */}
      <div className="flex-1 flex flex-col bg-white rounded-xl border shadow-sm">
        <div className="p-4 border-b">
          <h2 className="font-medium text-sm">RAG 智能问答</h2>
          {selectedDoc && (
            <p className="text-xs text-gray-400 mt-1">基于文档：{selectedDoc}</p>
          )}
        </div>

        {/* 聊天记录 */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {chatHistory.length === 0 && (
            <p className="text-sm text-gray-400 text-center mt-8">
              选择一份文档，在下方输入问题开始分析
            </p>
          )}
          {chatHistory.map((msg, i) => (
            <div key={`${msg.role}-${i}-${msg.content.slice(0, 20)}`} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-xl p-3 text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-800'
              }`}>
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-gray-200">
                    <p className="text-xs font-medium text-gray-500 mb-1">📎 来源引用</p>
                    {msg.sources.slice(0, 3).map((src, j) => (
                      <div key={j} className="text-xs text-gray-500 mt-1">
                        <span className="font-medium">{src.source}</span> · 第{src.page}页 · 相关度 {(src.score * 100).toFixed(0)}%
                        <p className="text-gray-400 line-clamp-2">{src.content}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {isChatting && (
            <div className="text-sm text-gray-400">分析中...</div>
          )}
          <div ref={chatEndRef} />
        </div>

        {chatError && (
          <div className="px-4 py-2 bg-red-50 text-xs text-red-700">{chatError}</div>
        )}

        {/* 输入区 */}
        <div className="p-4 border-t flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { handleSend().catch(() => {}); } }}
            placeholder="输入问题..."
            aria-label="输入分析问题"
            className="flex-1 px-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400"
          />
          <button
            onClick={handleSend}
            disabled={!canSend}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
              canSend
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            }`}
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
