import { create } from 'zustand';

/** 已上传文档 */
export interface DocInfo {
  filename: string;
  chunk_count: number;
  page_count: number;
  file_size: number;
  upload_time: string;
}

/** 聊天消息 */
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{
    content: string;
    source: string;
    page: number;
    score: number;
  }>;
}

/** 文档状态 */
interface DocumentState {
  documents: DocInfo[];
  isUploading: boolean;
  uploadError: string | null;
  chatHistory: ChatMessage[];
  isChatting: boolean;
  chatError: string | null;

  // Actions
  setDocuments: (docs: DocInfo[]) => void;
  addDocument: (doc: DocInfo) => void;
  setIsUploading: (v: boolean) => void;
  setUploadError: (e: string | null) => void;
  addMessage: (msg: ChatMessage) => void;
  setIsChatting: (v: boolean) => void;
  setChatError: (e: string | null) => void;
  clearChat: () => void;
}

export const useDocumentStore = create<DocumentState>((set) => ({
  documents: [],
  isUploading: false,
  uploadError: null,
  chatHistory: [],
  isChatting: false,
  chatError: null,

  setDocuments: (documents) => set({ documents }),
  addDocument: (doc) => set((s) => ({ documents: [...s.documents, doc] })),
  setIsUploading: (isUploading) => set({ isUploading }),
  setUploadError: (uploadError) => set({ uploadError }),
  addMessage: (msg) => set((s) => ({ chatHistory: [...s.chatHistory, msg] })),
  setIsChatting: (isChatting) => set({ isChatting }),
  setChatError: (chatError) => set({ chatError }),
  clearChat: () => set({ chatHistory: [] }),
}));
