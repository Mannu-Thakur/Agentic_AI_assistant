import { apiRequestWithWakeup } from './api';

export interface UploadedDocument {
  id: string;
  user_id: string;
  chat_id?: string | null;
  filename: string;
  file_type: string;
  size_bytes: number;
  status: 'processing' | 'ready' | 'failed';
  stage: string;
  progress: number;
  chunk_count: number;
  error_message?: string | null;
  uploaded_at: string;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function uploadDocument(
  file: File,
  chatId?: string,
): Promise<UploadedDocument> {
  const body = new FormData();
  body.append('file', file);
  if (chatId) body.append('chat_id', chatId);

  return apiRequestWithWakeup<UploadedDocument>('/documents/upload', {
    method: 'POST',
    body,
    timeoutMs: 180_000,
  });
}

/** Poll the server's persisted stage, never marking a still-running job as failed locally. */
export async function waitForDocumentReady(
  documentId: string,
  options: {
    onProgress?: (document: UploadedDocument) => void;
    timeoutMs?: number;
    pollIntervalMs?: number;
  } = {},
): Promise<UploadedDocument> {
  const timeoutMs = options.timeoutMs ?? 10 * 60_000;
  const pollIntervalMs = options.pollIntervalMs ?? 1_000;
  const deadline = Date.now() + timeoutMs;
  let consecutiveErrors = 0;
  let lastError: unknown;

  while (Date.now() < deadline) {
    let doc: UploadedDocument;
    try {
      doc = await apiRequestWithWakeup<UploadedDocument>(
        `/documents/${encodeURIComponent(documentId)}/status`,
      );
      consecutiveErrors = 0;
      lastError = undefined;
    } catch (error) {
      consecutiveErrors += 1;
      lastError = error;
      if (consecutiveErrors >= 5) {
        throw new Error(
          `Could not read indexing status after 5 attempts: ${error instanceof Error ? error.message : 'backend unavailable'}`,
        );
      }
      await sleep(pollIntervalMs);
      continue;
    }

    options.onProgress?.(doc);
    if (doc.status === 'ready') return doc;
    if (doc.status === 'failed') {
      throw new Error(doc.error_message || `Indexing failed during ${doc.stage || 'processing'}.`);
    }

    await sleep(pollIntervalMs);
  }

  throw new Error(
    `Document indexing is still running after ${Math.round(timeoutMs / 60_000)} minutes. ` +
      `Check its status and retry if it has failed.${lastError instanceof Error ? ` Last status error: ${lastError.message}` : ''}`,
  );
}

export async function uploadAndIndexDocument(
  file: File,
  chatId?: string,
  onProgress?: (document: UploadedDocument) => void,
): Promise<UploadedDocument> {
  const uploaded = await uploadDocument(file, chatId);
  onProgress?.(uploaded);
  if (uploaded.status === 'ready') return uploaded;
  if (uploaded.status === 'failed') {
    throw new Error(uploaded.error_message || 'The server rejected document indexing.');
  }
  return waitForDocumentReady(uploaded.id, { onProgress });
}
