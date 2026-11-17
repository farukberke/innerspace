import { describe, expect, it } from 'vitest'
import { buildDetails } from './EntryForm'

describe('buildDetails', () => {
  it('quick: mood only when given', () => {
    expect(buildDetails('quick', { mood: '' })).toEqual({})
    expect(buildDetails('quick', { mood: '3', sleep: '6.5' })).toEqual({ mood: 3, sleep_hours: 6.5 })
    expect(buildDetails('quick', { mood: '4' })).toEqual({ mood: 4 })
  })
  it('panic: sends only allowed keys and splits lists', () => {
    expect(buildDetails('panic', { intensity: '7', duration: '', symptoms: 'çarpıntı, nefes darlığı ', trigger: '' })).toEqual({
      intensity: 7,
      symptoms: ['çarpıntı', 'nefes darlığı'],
    })
  })
  it('medication and avoidance', () => {
    expect(buildDetails('medication', { medication_name: ' X ', taken: false, side_effects: '' })).toEqual({
      medication_name: 'X',
      taken: false,
      side_effects: [],
    })
    expect(buildDetails('avoidance', { situation: 'Metro', avoided: true, anxiety: '6' })).toEqual({
      situation: 'Metro',
      avoided: true,
      anxiety: 6,
    })
  })
})
