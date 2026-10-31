import { useCallback, useRef } from 'react';
import { useSettings } from '../contexts/SettingsContext';

/**
 * Hook for managing chat response notifications (system and sound)
 */
export function useNotifications() {
  const { settings } = useSettings();
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Initialize audio element on first use
  const getAudio = useCallback(() => {
    if (!audioRef.current) {
      audioRef.current = new Audio('./addons/just-maybe-577.mp3');
      audioRef.current.volume = 0.5; // Set to 50% volume
    }
    return audioRef.current;
  }, []);

  const playSound = useCallback(() => {
    try {
      const audio = getAudio();
      // Reset audio to start if already playing
      audio.currentTime = 0;
      audio.play().catch((error) => {
        console.warn('[Notifications] Failed to play sound:', error);
      });
    } catch (error) {
      console.error('[Notifications] Error playing sound:', error);
    }
  }, [getAudio]);

  const showSystemNotification = useCallback((title: string, body: string) => {
    if (!('Notification' in window)) {
      console.warn('[Notifications] Browser does not support notifications');
      return;
    }

    // Request permission if needed
    if (Notification.permission === 'default') {
      Notification.requestPermission().then((permission) => {
        if (permission === 'granted') {
          new Notification(title, { body, silent: true });
        }
      });
    } else if (Notification.permission === 'granted') {
      new Notification(title, { body, silent: true });
    }
  }, []);

  /**
   * Notify user of a new assistant response
   */
  const notifyResponse = useCallback(
    (preview?: string) => {
      const showSystem = settings.showSystemNotification ?? true;
      const shouldPlaySound = settings.playSoundNotification ?? false;

      console.log('[Notifications] Triggering notification', { showSystem, shouldPlaySound });

      if (showSystem) {
        const body = preview 
          ? preview.substring(0, 100) + (preview.length > 100 ? '...' : '')
          : 'Your question has been answered';
        showSystemNotification('Assistant Response Ready', body);
      }

      if (shouldPlaySound) {
        playSound();
      }
    },
    [settings.showSystemNotification, settings.playSoundNotification, showSystemNotification, playSound]
  );

  return { notifyResponse };
}
