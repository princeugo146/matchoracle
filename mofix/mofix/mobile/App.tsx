import React, { useEffect, useRef, useState } from 'react';
import {
  StatusBar,
  StyleSheet,
  View,
  BackHandler,
  Platform,
  Alert,
} from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import * as SplashScreen from 'expo-splash-screen';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';

import SplashScreenComponent from './screens/SplashScreen';
import WebViewScreen from './screens/WebViewScreen';

// Keep the splash screen visible while we fetch resources
SplashScreen.preventAutoHideAsync();

// Configure notification handler
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export type RootStackParamList = {
  Splash: undefined;
  WebView: { url?: string };
};

const Stack = createStackNavigator<RootStackParamList>();

const WEB_APP_URL =
  Constants.expoConfig?.extra?.webAppUrl ||
  'https://matchoracle-production.up.railway.app';

export default function App() {
  const [appIsReady, setAppIsReady] = useState(false);
  const [showSplash, setShowSplash] = useState(true);
  const notificationListener = useRef<Notifications.Subscription>();
  const responseListener = useRef<Notifications.Subscription>();

  useEffect(() => {
    async function prepare() {
      try {
        // Register for push notifications
        await registerForPushNotificationsAsync();

        // Simulate minimum splash duration (1.5s)
        await new Promise(resolve => setTimeout(resolve, 1500));
      } catch (e) {
        console.warn('App prepare error:', e);
      } finally {
        setAppIsReady(true);
        await SplashScreen.hideAsync();
      }
    }

    prepare();

    // Notification listeners
    notificationListener.current = Notifications.addNotificationReceivedListener(
      notification => {
        console.log('Notification received:', notification);
      }
    );

    responseListener.current = Notifications.addNotificationResponseReceivedListener(
      response => {
        const url = response.notification.request.content.data?.url as string;
        if (url) {
          // Navigate to specific URL when notification is tapped
          console.log('Navigate to:', url);
        }
      }
    );

    return () => {
      if (notificationListener.current) {
        Notifications.removeNotificationSubscription(notificationListener.current);
      }
      if (responseListener.current) {
        Notifications.removeNotificationSubscription(responseListener.current);
      }
    };
  }, []);

  const handleSplashFinish = () => {
    setShowSplash(false);
  };

  if (!appIsReady) {
    return null;
  }

  return (
    <NavigationContainer>
      <StatusBar
        barStyle="light-content"
        backgroundColor="#030508"
        translucent={false}
      />
      <Stack.Navigator
        screenOptions={{ headerShown: false, animationEnabled: true }}
        initialRouteName={showSplash ? 'Splash' : 'WebView'}
      >
        <Stack.Screen name="Splash">
          {props => (
            <SplashScreenComponent
              {...props}
              onFinish={handleSplashFinish}
            />
          )}
        </Stack.Screen>
        <Stack.Screen
          name="WebView"
          initialParams={{ url: WEB_APP_URL }}
          component={WebViewScreen}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

async function registerForPushNotificationsAsync(): Promise<string | null> {
  let token: string | null = null;

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'MatchOracle',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#00d4ff',
    });
  }

  if (Device.isDevice) {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== 'granted') {
      console.log('Push notification permission not granted');
      return null;
    }

    try {
      const projectId = Constants.expoConfig?.extra?.eas?.projectId;
      if (projectId) {
        token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
      }
    } catch (e) {
      console.log('Push token error:', e);
    }
  }

  return token;
}
