import { useSyncExternalStore } from 'react'
import { mediaKey, watchMediaKey } from '../../../apps/desktop/ui/src/api'

export const useMediaKey = () => useSyncExternalStore(watchMediaKey, mediaKey, mediaKey)
