const ACTIVE_USER_KEY = 'cheat_clip_active_user';

function scopedKey(key: string): string {
  const userId = localStorage.getItem(ACTIVE_USER_KEY);
  return userId ? `cheat_clip_user_${encodeURIComponent(userId)}_${key}` : key;
}

export const accountStorage = {
  getItem(key: string): string | null {
    return localStorage.getItem(scopedKey(key));
  },
  setItem(key: string, value: string): void {
    localStorage.setItem(scopedKey(key), value);
  },
  removeItem(key: string): void {
    localStorage.removeItem(scopedKey(key));
  },
  get length(): number {
    const prefix = scopedKey('');
    let count = 0;
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key?.startsWith(prefix)) count += 1;
    }
    return count;
  },
  key(index: number): string | null {
    const prefix = scopedKey('');
    let current = 0;
    for (let storageIndex = 0; storageIndex < localStorage.length; storageIndex += 1) {
      const key = localStorage.key(storageIndex);
      if (!key?.startsWith(prefix)) continue;
      if (current === index) return key.slice(prefix.length);
      current += 1;
    }
    return null;
  },
};
