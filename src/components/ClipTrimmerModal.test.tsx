import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ClipTrimmerModal } from './ClipTrimmerModal';
import { LanguageProvider } from '../locales';
import type { YouTubePlayer, YouTubePlayerOptions, ViralClip } from '../types';

const createClip = (start: number, end: number): ViralClip => ({
  title: 'Test clip',
  start_time: start,
  end_time: end,
  virality_score: 90,
  key_quotes: [],
  transcript: 'Test transcript',
});

const players: FakeYouTubePlayer[] = [];

class FakeYouTubePlayer implements YouTubePlayer {
  destroy = vi.fn();
  loadVideoById = vi.fn();
  seekTo = vi.fn();
  pauseVideo = vi.fn();
  playVideo = vi.fn();
  mute = vi.fn();
  unMute = vi.fn();
  getPlayerState = vi.fn(() => 0);
  getCurrentTime = vi.fn(() => 0);
  unloadModule = vi.fn();
  private options: YouTubePlayerOptions;

  constructor(_element: string | HTMLElement, options: YouTubePlayerOptions) {
    this.options = options;
    players.push(this);
  }

  ready() {
    const onReady = this.options.events?.onReady;
    if (!onReady) return false;
    onReady({ target: this });
    return true;
  }
}

describe('ClipTrimmerModal YouTube player', () => {
  beforeEach(() => {
    players.length = 0;
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    delete window.YT;
  });

  it('seeks the player to the selected clip and responds to trim controls', async () => {
    vi.useFakeTimers();
    window.YT = { Player: FakeYouTubePlayer };

    render(
      <LanguageProvider>
        <ClipTrimmerModal
          isOpen
          clip={createClip(120, 180)}
          videoId="youtube-video"
          videoDuration={600}
          onClose={vi.fn()}
          onDownload={vi.fn()}
        />
      </LanguageProvider>,
    );

    await act(async () => {
      vi.advanceTimersByTime(60);
      await Promise.resolve();
    });
    let playerReady: boolean | undefined;
    act(() => {
      playerReady = players[0].ready();
    });

    expect(playerReady).toBe(true);
    expect(players).toHaveLength(1);
    expect(players[0].seekTo).toHaveBeenCalledWith(120, true);
    const startButtons = screen.getAllByRole('button', { name: '+5s' });
    fireEvent.click(startButtons[0]);

    expect(players[0].seekTo).toHaveBeenLastCalledWith(125, true);
    expect(screen.getByDisplayValue('2:05')).toBeTruthy();
  });

  it('recreates the player with the new clip start instead of a stale trim value', async () => {
    vi.useFakeTimers();
    window.YT = { Player: FakeYouTubePlayer };

    const renderModal = (clip: ViralClip) => (
      <LanguageProvider>
        <ClipTrimmerModal
          isOpen
          clip={clip}
          videoId="youtube-video"
          videoDuration={600}
          onClose={vi.fn()}
          onDownload={vi.fn()}
        />
      </LanguageProvider>
    );

    const { rerender } = render(renderModal(createClip(120, 180)));
    await act(async () => {
      vi.advanceTimersByTime(60);
      await Promise.resolve();
    });
    act(() => players[0].ready());

    rerender(renderModal(createClip(240, 300)));
    await act(async () => {
      vi.advanceTimersByTime(60);
      await Promise.resolve();
    });
    let nextPlayerReady: boolean | undefined;
    act(() => {
      nextPlayerReady = players[1].ready();
    });

    expect(nextPlayerReady).toBe(true);
    expect(screen.getByDisplayValue('4:00')).toBeTruthy();
    expect(players).toHaveLength(2);
    expect(players[0].destroy).toHaveBeenCalledOnce();
    expect(players[1].seekTo).toHaveBeenCalledWith(240, true);
  });

  it('does not poll or call the YouTube player before its ready event', async () => {
    vi.useFakeTimers();
    window.YT = { Player: FakeYouTubePlayer };

    render(
      <LanguageProvider>
        <ClipTrimmerModal
          isOpen
          clip={createClip(120, 180)}
          videoId="youtube-video"
          videoDuration={600}
          onClose={vi.fn()}
          onDownload={vi.fn()}
        />
      </LanguageProvider>,
    );

    await act(async () => {
      vi.advanceTimersByTime(60);
      await Promise.resolve();
    });
    expect(players).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(players[0].getCurrentTime).not.toHaveBeenCalled();

    act(() => players[0].ready());
    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(players[0].getCurrentTime).toHaveBeenCalledOnce();
  });
});
