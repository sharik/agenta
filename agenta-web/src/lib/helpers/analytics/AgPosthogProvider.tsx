import {useCallback, useEffect, useState} from "react"
import {useRouter} from "next/router"
import {useAtom} from "jotai"
import {posthogAtom, type PostHogConfig} from "./store/atoms"
import {CustomPosthogProviderType} from "./types"
import {isDemo} from "../utils"

const CustomPosthogProvider: CustomPosthogProviderType = ({children}) => {
    const router = useRouter()
    const [loadingPosthog, setLoadingPosthog] = useState(false)
    const [posthogClient, setPosthogClient] = useAtom(posthogAtom)

    const initPosthog = useCallback(async () => {
        if (!!posthogClient) return
        if (loadingPosthog) return

        setLoadingPosthog(true)

        try {
            const posthog = (await import("posthog-js")).default

            posthog.init(process.env.NEXT_PUBLIC_POSTHOG_API_KEY!, {
                api_host: "https://app.posthog.com",
                // Enable debug mode in development
                loaded: (posthog) => {
                    setPosthogClient(posthog)
                    if (process.env.NODE_ENV === "development") posthog.debug()
                },
                capture_pageview: false,
                ...(isDemo()
                    ? {
                          session_recording: {
                              maskAllInputs: false,
                              maskInputOptions: {
                                  password: true,
                                  email: true,
                              },
                          },
                      }
                    : {persistence: "localStorage+cookie"}),
            })
        } finally {
            setLoadingPosthog(false)
        }
    }, [loadingPosthog, posthogClient, setPosthogClient])

    useEffect(() => {
        initPosthog()
    }, [initPosthog])

    const handleRouteChange = useCallback(() => {
        posthogClient?.capture("$pageview", {$current_url: window.location.href})
    }, [posthogClient])

    useEffect(() => {
        router.events.on("routeChangeComplete", handleRouteChange)

        return () => {
            router.events.off("routeChangeComplete", handleRouteChange)
        }
    }, [handleRouteChange, router.events])

    return <>{children}</>
}

export default CustomPosthogProvider
