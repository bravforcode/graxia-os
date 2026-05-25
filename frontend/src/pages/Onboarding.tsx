import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'

type Step = 'welcome' | 'profile' | 'first_scan' | 'complete'

interface OnboardingState {
  user_id: string
  current_step: Step
  completed_steps: string[]
  profile_data: Record<string, unknown> | null
  first_scan_completed: boolean
  is_complete: boolean
}

const STEPS: { id: Step; label: string }[] = [
  { id: 'welcome', label: 'Welcome' },
  { id: 'profile', label: 'Profile' },
  { id: 'first_scan', label: 'First Scan' },
  { id: 'complete', label: 'Complete' },
]

export default function Onboarding() {
  const navigate = useNavigate()
  const [state, setState] = useState<OnboardingState | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Form state for profile step
  const [profile, setProfile] = useState({
    full_name: '',
    title: '',
    company: '',
    location: '',
    bio: '',
    skills: [] as string[],
    industries: [] as string[],
    goals: [] as string[],
  })
  const [skillInput, setSkillInput] = useState('')
  const [industryInput, setIndustryInput] = useState('')

  useEffect(() => {
    fetchState()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const fetchState = async () => {
    try {
      const { data } = await api.getOnboardingState()
      setState(data)
      if (data.is_complete) {
        navigate('/dashboard', { replace: true })
      }
      if (data.profile_data) {
        setProfile(prev => ({ ...prev, ...data.profile_data }))
      }
    } catch (e) {
      setError('Failed to load onboarding state')
    }
  }

  const advanceStep = async (step: Step, data?: Record<string, unknown>) => {
    setLoading(true)
    setError('')
    try {
      const { data: newState } = await api.updateOnboardingProgress(step, data)
      setState(newState)
      if (newState.is_complete) {
        navigate('/dashboard', { replace: true })
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setError(err.response?.data?.detail || 'Failed to advance step')
    } finally {
      setLoading(false)
    }
  }

  const skipOnboarding = async () => {
    setLoading(true)
    try {
      const { data } = await api.skipOnboarding()
      setState(data)
      navigate('/dashboard', { replace: true })
    } catch (e) {
      setError('Failed to skip onboarding')
    } finally {
      setLoading(false)
    }
  }

  const handleAddSkill = () => {
    if (skillInput.trim() && !profile.skills.includes(skillInput.trim())) {
      setProfile({ ...profile, skills: [...profile.skills, skillInput.trim()] })
      setSkillInput('')
    }
  }

  const handleRemoveSkill = (skill: string) => {
    setProfile({ ...profile, skills: profile.skills.filter(s => s !== skill) })
  }

  const handleAddIndustry = () => {
    if (industryInput.trim() && !profile.industries.includes(industryInput.trim())) {
      setProfile({ ...profile, industries: [...profile.industries, industryInput.trim()] })
      setIndustryInput('')
    }
  }

  const handleRemoveIndustry = (ind: string) => {
    setProfile({ ...profile, industries: profile.industries.filter(i => i !== ind) })
  }

  const currentStepIndex = state ? STEPS.findIndex(s => s.id === state.current_step) : 0

  if (!state) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Progress bar */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">Getting Started</h1>
            <button
              onClick={skipOnboarding}
              disabled={loading}
              className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            >
              Skip for now →
            </button>
          </div>
          <div className="flex items-center space-x-2">
            {STEPS.map((step, idx) => (
              <div key={step.id} className="flex items-center flex-1">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ${
                    idx < currentStepIndex
                      ? 'bg-green-500 text-white'
                      : idx === currentStepIndex
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
                  }`}
                >
                  {idx < currentStepIndex ? '✓' : idx + 1}
                </div>
                <span
                  className={`ml-2 text-sm hidden sm:block ${
                    idx === currentStepIndex
                      ? 'text-blue-600 dark:text-blue-400 font-medium'
                      : 'text-gray-500 dark:text-gray-400'
                  }`}
                >
                  {step.label}
                </span>
                {idx < STEPS.length - 1 && (
                  <div
                    className={`flex-1 h-1 mx-4 rounded ${
                      idx < currentStepIndex
                        ? 'bg-green-500'
                        : 'bg-gray-200 dark:bg-gray-700'
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Step content */}
      <div className="max-w-2xl mx-auto px-4 py-12">
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400">
            {error}
          </div>
        )}

        {state.current_step === 'welcome' && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
            <div className="text-center mb-8">
              <div className="w-20 h-20 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
                <span className="text-4xl">🎯</span>
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
                Welcome to Graxia
              </h2>
              <p className="text-gray-600 dark:text-gray-400 max-w-md mx-auto">
                Your AI-powered business development co-pilot. Let's set up your profile 
                in 3 simple steps to start finding high-value opportunities.
              </p>
            </div>
            <div className="space-y-4 mb-8">
              {[
                { icon: '🤖', text: 'AI scans 100+ sources for relevant opportunities' },
                { icon: '📊', text: 'Auto-scoring ranks leads by your criteria' },
                { icon: '✍️', text: 'One-click personalized outreach drafts' },
                { icon: '📈', text: 'Track pipeline from first contact to closed deal' },
              ].map((item, i) => (
                <div key={i} className="flex items-center space-x-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <span className="text-2xl">{item.icon}</span>
                  <span className="text-gray-700 dark:text-gray-300">{item.text}</span>
                </div>
              ))}
            </div>
            <button
              onClick={() => advanceStep('profile')}
              disabled={loading}
              className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-lg transition-colors"
            >
              {loading ? 'Loading...' : 'Get Started →'}
            </button>
          </div>
        )}

        {state.current_step === 'profile' && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Your Profile</h2>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              This helps our AI find opportunities that match your expertise and goals.
            </p>
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Full Name *
                  </label>
                  <input
                    type="text"
                    value={profile.full_name}
                    onChange={e => setProfile({ ...profile, full_name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="Jane Smith"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Professional Title
                  </label>
                  <input
                    type="text"
                    value={profile.title}
                    onChange={e => setProfile({ ...profile, title: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="e.g., Full-Stack Developer"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Company / Freelance
                  </label>
                  <input
                    type="text"
                    value={profile.company}
                    onChange={e => setProfile({ ...profile, company: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="e.g., Acme Inc. or Freelance"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Location
                  </label>
                  <input
                    type="text"
                    value={profile.location}
                    onChange={e => setProfile({ ...profile, location: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="e.g., Bangkok, Thailand"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Skills (press Enter to add)
                </label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {profile.skills.map(skill => (
                    <span
                      key={skill}
                      className="inline-flex items-center px-3 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full text-sm"
                    >
                      {skill}
                      <button
                        onClick={() => handleRemoveSkill(skill)}
                        className="ml-2 text-blue-500 hover:text-blue-700"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={skillInput}
                    onChange={e => setSkillInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAddSkill())}
                    className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="e.g., React, Python, AI/ML"
                  />
                  <button
                    onClick={handleAddSkill}
                    className="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg text-gray-700 dark:text-gray-300"
                  >
                    Add
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Industries (press Enter to add)
                </label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {profile.industries.map(ind => (
                    <span
                      key={ind}
                      className="inline-flex items-center px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full text-sm"
                    >
                      {ind}
                      <button
                        onClick={() => handleRemoveIndustry(ind)}
                        className="ml-2 text-green-500 hover:text-green-700"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={industryInput}
                    onChange={e => setIndustryInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAddIndustry())}
                    className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    placeholder="e.g., Fintech, Healthcare, SaaS"
                  />
                  <button
                    onClick={handleAddIndustry}
                    className="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg text-gray-700 dark:text-gray-300"
                  >
                    Add
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Brief Bio
                </label>
                <textarea
                  value={profile.bio}
                  onChange={e => setProfile({ ...profile, bio: e.target.value })}
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white resize-none"
                  placeholder="Tell us about your experience, what you're looking for..."
                />
              </div>
            </div>
            <div className="flex gap-3 mt-8">
              <button
                onClick={() => advanceStep('welcome')}
                disabled={loading}
                className="px-6 py-3 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                ← Back
              </button>
              <button
                onClick={() => advanceStep('first_scan', profile)}
                disabled={loading || !profile.full_name.trim()}
                className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-lg transition-colors"
              >
                {loading ? 'Saving...' : 'Continue →'}
              </button>
            </div>
          </div>
        )}

        {state.current_step === 'first_scan' && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="w-20 h-20 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
              <span className="text-4xl">🔍</span>
            </div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
              Running Your First Scan
            </h2>
            <p className="text-gray-600 dark:text-gray-400 mb-8 max-w-md mx-auto">
              Our AI is now scanning 100+ sources to find opportunities that match your profile. 
              This takes about 30 seconds.
            </p>
            <div className="w-full max-w-md mx-auto bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-8 overflow-hidden">
              <div className="bg-blue-600 h-2 rounded-full animate-pulse w-3/4"></div>
            </div>
            <button
              onClick={() => advanceStep('complete')}
              disabled={loading}
              className="px-8 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-lg transition-colors"
            >
              {loading ? 'Scanning...' : 'View Results →'}
            </button>
          </div>
        )}

        {state.current_step === 'complete' && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
            <div className="w-20 h-20 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
              <span className="text-4xl">🎉</span>
            </div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
              You're All Set!
            </h2>
            <p className="text-gray-600 dark:text-gray-400 mb-8 max-w-md mx-auto">
              Your profile is complete and your first opportunities are ready. 
              Check your dashboard daily for new AI-scored leads.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8 max-w-lg mx-auto">
              {[
                { number: '10+', label: 'Opportunities Found' },
                { number: '3', label: 'High-Score Matches' },
                { number: '24/7', label: 'AI Monitoring' },
              ].map((stat, i) => (
                <div key={i} className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{stat.number}</div>
                  <div className="text-sm text-gray-600 dark:text-gray-400">{stat.label}</div>
                </div>
              ))}
            </div>
            <button
              onClick={() => navigate('/dashboard')}
              className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition-colors"
            >
              Go to Dashboard →
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
