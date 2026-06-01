import React, { useRef, useState, useCallback } from 'react';
import {
  View,
  StyleSheet,
  BackHandler,
  ActivityIndicator,
  Text,
  TouchableOpacity,
  StatusBar,
  Platform,
  Linking,
} from 'react-native';
import { WebView, WebViewNavigation } from 'react-native-webview';
import { useFocusEffect } from '@react-navigation/native';
import { StackNavigationProp } from '@react-navigation/stack';
import { RouteProp } from '@react-navigation/native';
import Constants from 'expo-constants';
import { RootStackParamList } from '../App';

const WEB_APP_URL =
  Constants.expoConfig?.extra?.webAppUrl ||
  'https://matchoracle-production.up.railway.app';

// URLs that should open in the external browser
const EXTERNAL_URL_PATTERNS = [
  'paystack.com',
  'paystack.co',
  'google.com/accounts',
  'accounts.google.com',
];

interface Props {
  navigation: StackNavigationProp<RootStackParamList, 'WebView'>;
  route: RouteProp<RootStackParamList, 'WebView'>;
}

export default function WebViewScreen({ navigation, route }: Props) {
  const webViewRef = useRef<WebView>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [currentUrl, setCurrentUrl] = useState(route.params?.url || WEB_APP_URL);

  // Handle Android back button
  useFocusEffect(
    useCallback(() => {
      const onBackPress = () => {
        if (canGoBack && webViewRef.current) {
          webViewRef.current.goBack();
          return true; // Prevent default back action
        }
        return false; // Allow default back action (exit app)
      };

      const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
      return () => subscription.remove();
    }, [canGoBack])
  );

  const handleNavigationStateChange = (navState: WebViewNavigation) => {
    setCanGoBack(navState.canGoBack);
    setCurrentUrl(navState.url);
  };

  const handleShouldStartLoadWithRequest = (request: { url: string }) => {
    const url = request.url;

    // Open external payment/auth URLs in browser
    const isExternal = EXTERNAL_URL_PATTERNS.some(pattern => url.includes(pattern));
    if (isExternal) {
      Linking.openURL(url).catch(err => console.error('Cannot open URL:', err));
      return false;
    }

    // Allow all other URLs
    return true;
  };

  const handleLoadStart = () => {
    setIsLoading(true);
    setHasError(false);
  };

  const handleLoadEnd = () => {
    setIsLoading(false);
  };

  const handleError = () => {
    setIsLoading(false);
    setHasError(true);
  };

  const handleReload = () => {
    setHasError(false);
    setIsLoading(true);
    webViewRef.current?.reload();
  };

  // Injected JavaScript for native enhancements
  const injectedJS = `
    (function() {
      // Mark as native app
      window.isNativeApp = true;
      window.platform = 'android';

      // Prevent zoom on input focus (iOS)
      const meta = document.querySelector('meta[name="viewport"]');
      if (meta) {
        meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
      }

      // Smooth scrolling
      document.documentElement.style.scrollBehavior = 'smooth';

      // Hide PWA install banner (we're already native)
      const installBanner = document.getElementById('installBanner');
      if (installBanner) installBanner.style.display = 'none';

      // Override localStorage for install dismissed
      try {
        localStorage.setItem('installDismissed', '1');
      } catch(e) {}

      true; // Required for injectedJavaScript
    })();
  `;

  if (hasError) {
    return (
      <View style={styles.errorContainer}>
        <StatusBar barStyle="light-content" backgroundColor="#030508" />
        <Text style={styles.errorIcon}>⚽</Text>
        <Text style={styles.errorTitle}>Connection Error</Text>
        <Text style={styles.errorText}>
          Unable to connect to MatchOracle.{'\n'}
          Please check your internet connection and try again.
        </Text>
        <TouchableOpacity style={styles.retryButton} onPress={handleReload}>
          <Text style={styles.retryText}>Try Again</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.retryButton, styles.homeButton]}
          onPress={() => {
            setHasError(false);
            setCurrentUrl(WEB_APP_URL);
          }}
        >
          <Text style={styles.retryText}>Go to Home</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#030508" />

      <WebView
        ref={webViewRef}
        source={{ uri: currentUrl }}
        style={styles.webview}
        onNavigationStateChange={handleNavigationStateChange}
        onShouldStartLoadWithRequest={handleShouldStartLoadWithRequest}
        onLoadStart={handleLoadStart}
        onLoadEnd={handleLoadEnd}
        onError={handleError}
        injectedJavaScript={injectedJS}
        javaScriptEnabled={true}
        domStorageEnabled={true}
        allowsBackForwardNavigationGestures={true}
        pullToRefreshEnabled={true}
        cacheEnabled={true}
        cacheMode="LOAD_DEFAULT"
        mixedContentMode="compatibility"
        allowsInlineMediaPlayback={true}
        mediaPlaybackRequiresUserAction={false}
        userAgent={`MatchOracle/1.0.0 (Android; Mobile) AppleWebKit/537.36`}
        // Android-specific
        androidLayerType="hardware"
        overScrollMode="never"
        // iOS-specific
        bounces={false}
        scrollEnabled={true}
        showsHorizontalScrollIndicator={false}
        showsVerticalScrollIndicator={false}
        decelerationRate="normal"
        keyboardDisplayRequiresUserAction={false}
        automaticallyAdjustContentInsets={false}
        contentInsetAdjustmentBehavior="never"
      />

      {/* Loading overlay */}
      {isLoading && (
        <View style={styles.loadingOverlay}>
          <View style={styles.loadingCard}>
            <ActivityIndicator size="large" color="#00d4ff" />
            <Text style={styles.loadingText}>Loading MatchOracle…</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#030508',
  },
  webview: {
    flex: 1,
    backgroundColor: '#030508',
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: '#030508',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
  },
  loadingCard: {
    alignItems: 'center',
    gap: 16,
  },
  loadingText: {
    color: '#94a3b8',
    fontSize: 14,
    marginTop: 12,
    letterSpacing: 0.5,
  },
  errorContainer: {
    flex: 1,
    backgroundColor: '#030508',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 40,
  },
  errorIcon: {
    fontSize: 56,
    marginBottom: 20,
  },
  errorTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#f0f6ff',
    marginBottom: 12,
    textAlign: 'center',
  },
  errorText: {
    fontSize: 14,
    color: '#94a3b8',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 32,
  },
  retryButton: {
    backgroundColor: '#00d4ff',
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 10,
    marginBottom: 12,
    minWidth: 180,
    alignItems: 'center',
  },
  homeButton: {
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
  },
  retryText: {
    color: '#030508',
    fontWeight: '700',
    fontSize: 15,
  },
});
