// Poll sequentially; a slow response never creates overlapping requests.
export async function pollUploadJob(fetchJob, onStatus, {
  signal,
  now = Date.now,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
} = {}) {
  const deadline = now() + 12 * 60 * 1000;
  let delay = 5000;
  let failures = 0;
  let previousProgress;
  while (now() < deadline) {
    if (signal?.aborted) throw Object.assign(new Error('Cancelled'), { code: 'ERR_CANCELED' });
    try {
      const job = await fetchJob();
      if (signal?.aborted) throw Object.assign(new Error('Cancelled'), { code: 'ERR_CANCELED' });
      failures = 0;
      onStatus?.(job.status, job);
      if (job.status === 'completed') return job;
      if (job.status === 'failed') {
        throw Object.assign(new Error(job.error || 'Không thể xử lý tài liệu.'), {
          friendlyMessage: job.error || 'Không thể xử lý tài liệu.', terminal: true,
        });
      }
      const progress = `${job.status}:${job.stage}:${job.completed_pages}`;
      delay = progress === previousProgress ? Math.min(delay + 2500, 15000) : 5000;
      previousProgress = progress;
    } catch (error) {
      if (signal?.aborted || error.code === 'ERR_CANCELED' || error.terminal) throw error;
      const status = error.response?.status;
      if (status === 404) {
        error.friendlyMessage = 'Không tìm thấy tác vụ hoặc bạn không có quyền xem. Hãy kiểm tra tài khoản và Lịch sử trước khi tải lại file.';
        throw error;
      }
      const transient = [429, 500, 502, 503, 504].includes(status)
        || ['ERR_NETWORK', 'ECONNABORTED', 'ETIMEDOUT'].includes(error.code);
      if (!transient) throw error;
      failures += 1;
      if (failures >= 8) {
        error.friendlyMessage = 'Tạm thời không lấy được tiến độ xử lý. Hãy kiểm tra Lịch sử sau ít phút trước khi tải lại file.';
        throw error;
      }
      const retryAfter = error.response?.headers?.['retry-after'];
      const seconds = Number(retryAfter);
      const advised = retryAfter
        ? (Number.isFinite(seconds) ? seconds * 1000 : Date.parse(retryAfter) - now()) : 0;
      delay = Math.max(Math.min(60000, delay * 2), Number.isFinite(advised) ? advised : 0);
      onStatus?.('reconnecting', { stage: 'reconnecting' });
    }
    const remaining = deadline - now();
    if (remaining > 0) await sleep(Math.min(delay, remaining));
  }
  throw Object.assign(new Error('Job polling deadline exceeded'), {
    friendlyMessage: 'Tài liệu chưa hoàn tất trong thời gian chờ. Hãy kiểm tra Lịch sử sau ít phút.',
  });
}
