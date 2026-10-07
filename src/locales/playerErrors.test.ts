import { describe, expect, it } from 'vitest';
import { en } from './en';
import { id } from './id';

describe('localized video playback diagnostics', () => {
  it('explains common YouTube iframe playback errors', () => {
    expect(en.errors.youtubePlaybackError(101)).toContain('does not allow playback');
    expect(en.errors.youtubePlaybackError(153)).toContain('referrer');
    expect(id.errors.youtubePlaybackError(100)).toContain('tidak tersedia');
  });

  it('distinguishes local video network, decode, and format errors', () => {
    expect(en.errors.videoPlaybackError(2)).toContain('backend');
    expect(en.errors.videoPlaybackError(3)).toContain('decode');
    expect(id.errors.videoPlaybackError(4)).toContain('tidak didukung');
  });
});
