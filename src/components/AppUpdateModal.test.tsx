import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppUpdateModal } from './AppUpdateModal';
import { LanguageProvider } from '../locales';

describe('AppUpdateModal repository status', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('does not call unpublished local commits up to date', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      const data = url.endsWith('/version')
        ? {
            current_commit: '82ecbbf',
            commit_message: 'Local feature',
            branch: 'master',
          }
        : {
            current_commit: '82ecbbf',
            update_available: false,
            local_ahead_count: 1,
            behind_count: 0,
            remote_commit: 'a378f82',
            changelog: [],
          };

      return {
        ok: true,
        json: async () => data,
      };
    }));

    render(
      <LanguageProvider>
        <AppUpdateModal isOpen onClose={vi.fn()} />
      </LanguageProvider>,
    );

    expect(await screen.findByText('Local commits are not published')).toBeTruthy();
    expect(await screen.findByText(/GitHub \(currently a378f82\)/)).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByText("You're on the latest version!")).toBeNull();
    });
  });
});
