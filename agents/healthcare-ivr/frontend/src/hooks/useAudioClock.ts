import { useCallback, useRef, useState } from 'react'

/**
 * Tracks playback of an `<audio>` element. `attachAudio` is a callback ref, so it keeps working
 * when the element mounts after the first render (for example once the call has loaded).
 */
export function useAudioClock() {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isAttached, setIsAttached] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  const attachAudio = useCallback((audio: HTMLAudioElement | null) => {
    if (!audio) return
    audioRef.current = audio
    setIsAttached(true)

    const updateTime = () => setCurrentTime(audio.currentTime)
    const updateDuration = () => setDuration(Number.isFinite(audio.duration) ? audio.duration : 0)
    audio.addEventListener('timeupdate', updateTime)
    audio.addEventListener('seeked', updateTime)
    audio.addEventListener('durationchange', updateDuration)

    return () => {
      audio.removeEventListener('timeupdate', updateTime)
      audio.removeEventListener('seeked', updateTime)
      audio.removeEventListener('durationchange', updateDuration)
      audioRef.current = null
      setIsAttached(false)
    }
  }, [])

  const seek = useCallback((seconds: number) => {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = seconds
    setCurrentTime(seconds)
    // Playback can be refused (e.g. the audio failed to load); the seek still applies.
    audio.play().catch(() => undefined)
  }, [])

  return { attachAudio, currentTime, duration, canSeek: isAttached, seek }
}
