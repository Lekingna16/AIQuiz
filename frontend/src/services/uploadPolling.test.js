import { describe, expect, it, vi } from 'vitest';
import { pollUploadJob } from './uploadPolling';

function clock() {
  let time = 0;
  return { now: () => time, sleep: vi.fn(async (ms) => { time += ms; }) };
}

describe('upload job polling', () => {
  it('backs off on unchanged progress, resets when pages advance', async () => {
    const timing = clock();
    const job = { status: 'processing', stage: 'reading_pdf', completed_pages: 0 };
    const fetchJob = vi.fn()
      .mockResolvedValueOnce(job).mockResolvedValueOnce(job)
      .mockResolvedValueOnce({ ...job, completed_pages: 4 })
      .mockResolvedValueOnce({ status: 'completed', quiz_id: 'quiz' });
    const result = await pollUploadJob(fetchJob, null, timing);
    expect(result.quiz_id).toBe('quiz');
    expect(timing.sleep.mock.calls.map(([ms]) => ms)).toEqual([5000, 7500, 5000]);
  });

  it('honors Retry-After and recovers from a 503 without submitting another upload', async () => {
    const timing = clock();
    const fetchJob = vi.fn()
      .mockRejectedValueOnce({ response: { status: 429, headers: { 'retry-after': '60' } } })
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce({ status: 'completed' });
    await pollUploadJob(fetchJob, null, timing);
    expect(timing.sleep.mock.calls.map(([ms]) => ms)).toEqual([60000, 60000]);
    expect(fetchJob).toHaveBeenCalledTimes(3);
  });

  it('does not retry failed jobs or a missing job', async () => {
    for (const fetchJob of [
      vi.fn().mockResolvedValue({ status: 'failed', error: 'Gemini quota' }),
      vi.fn().mockRejectedValue({ response: { status: 404 } }),
    ]) {
      const timing = clock();
      await expect(pollUploadJob(fetchJob, null, timing)).rejects.toBeDefined();
      expect(fetchJob).toHaveBeenCalledTimes(1);
      expect(timing.sleep).not.toHaveBeenCalled();
    }
  });

  it('never retries sooner than a longer Retry-After header', async () => {
    const timing = clock();
    const fetchJob = vi.fn()
      .mockRejectedValueOnce({ response: { status: 429, headers: { 'retry-after': '120' } } })
      .mockResolvedValueOnce({ status: 'completed' });
    await pollUploadJob(fetchJob, null, timing);
    expect(timing.sleep).toHaveBeenCalledWith(120000);
  });

  it('stops issuing requests after the user leaves the upload page', async () => {
    const controller = new AbortController();
    const fetchJob = vi.fn().mockResolvedValue({ status: 'processing' });
    await expect(pollUploadJob(fetchJob, null, {
      ...clock(), signal: controller.signal, sleep: async () => controller.abort(),
    })).rejects.toHaveProperty('code', 'ERR_CANCELED');
    expect(fetchJob).toHaveBeenCalledTimes(1);
  });
});
