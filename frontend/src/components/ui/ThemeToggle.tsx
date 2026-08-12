import { Moon, SunMedium } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useUIStore } from '@/store/uiStore'

export function ThemeToggle() {
  const theme = useUIStore((state) => state.theme)
  const toggleTheme = useUIStore((state) => state.toggleTheme)

  return (
    <Button
      variant="secondary"
      size="sm"
      onClick={toggleTheme}
      icon={theme === 'dark' ? <SunMedium size={16} /> : <Moon size={16} />}
    >
      {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
    </Button>
  )
}
