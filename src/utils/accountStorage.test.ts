import { beforeEach, describe, expect, it } from 'vitest';
import { accountStorage } from './accountStorage';

describe('accountStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('isolates browser preferences and analysis history by signed-in account', () => {
    localStorage.setItem('cheat_clip_active_user', 'user-a');
    accountStorage.setItem('cheat_clip_cache_video-a', '{"title":"Private"}');

    localStorage.setItem('cheat_clip_active_user', 'user-b');
    expect(accountStorage.getItem('cheat_clip_cache_video-a')).toBeNull();
    accountStorage.setItem('cheat_clip_cache_video-b', '{"title":"Shared only with B"}');

    localStorage.setItem('cheat_clip_active_user', 'user-a');
    expect(accountStorage.getItem('cheat_clip_cache_video-a')).toBe('{"title":"Private"}');
    expect(accountStorage.length).toBe(1);
    expect(accountStorage.key(0)).toBe('cheat_clip_cache_video-a');
  });
});
