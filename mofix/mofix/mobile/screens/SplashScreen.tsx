import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
  Dimensions,
  StatusBar,
} from 'react-native';
import { StackNavigationProp } from '@react-navigation/stack';
import { RootStackParamList } from '../App';

const { width, height } = Dimensions.get('window');

interface Props {
  navigation: StackNavigationProp<RootStackParamList, 'Splash'>;
  onFinish: () => void;
}

export default function SplashScreen({ navigation, onFinish }: Props) {
  // Animation values
  const logoScale = useRef(new Animated.Value(0.3)).current;
  const logoOpacity = useRef(new Animated.Value(0)).current;
  const textOpacity = useRef(new Animated.Value(0)).current;
  const taglineOpacity = useRef(new Animated.Value(0)).current;
  const glowOpacity = useRef(new Animated.Value(0)).current;
  const progressWidth = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    StatusBar.setBarStyle('light-content');
    StatusBar.setBackgroundColor('#030508');

    // Sequence: logo appears → text fades in → tagline → progress bar → navigate
    Animated.sequence([
      // Logo scale + fade in
      Animated.parallel([
        Animated.spring(logoScale, {
          toValue: 1,
          tension: 60,
          friction: 8,
          useNativeDriver: true,
        }),
        Animated.timing(logoOpacity, {
          toValue: 1,
          duration: 600,
          useNativeDriver: true,
        }),
        Animated.timing(glowOpacity, {
          toValue: 1,
          duration: 800,
          useNativeDriver: true,
        }),
      ]),
      // Text fade in
      Animated.timing(textOpacity, {
        toValue: 1,
        duration: 400,
        useNativeDriver: true,
      }),
      // Tagline fade in
      Animated.timing(taglineOpacity, {
        toValue: 1,
        duration: 400,
        useNativeDriver: true,
      }),
    ]).start();

    // Progress bar animation
    Animated.timing(progressWidth, {
      toValue: width * 0.6,
      duration: 2200,
      delay: 400,
      useNativeDriver: false,
    }).start();

    // Navigate after splash
    const timer = setTimeout(() => {
      onFinish();
      navigation.replace('WebView', {});
    }, 3000);

    return () => clearTimeout(timer);
  }, []);

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#030508" />

      {/* Background glow effects */}
      <Animated.View style={[styles.glowTop, { opacity: glowOpacity }]} />
      <Animated.View style={[styles.glowBottom, { opacity: glowOpacity }]} />

      {/* Logo */}
      <Animated.View
        style={[
          styles.logoContainer,
          {
            transform: [{ scale: logoScale }],
            opacity: logoOpacity,
          },
        ]}
      >
        {/* Shield SVG rendered as View composition */}
        <View style={styles.shield}>
          <View style={styles.shieldInner}>
            <Text style={styles.shieldLetter}>M</Text>
          </View>
        </View>
      </Animated.View>

      {/* App Name */}
      <Animated.View style={{ opacity: textOpacity, alignItems: 'center' }}>
        <Text style={styles.appName}>
          <Text style={styles.appNameMatch}>MATCH</Text>
          <Text style={styles.appNameOracle}>ORACLE</Text>
        </Text>
      </Animated.View>

      {/* Tagline */}
      <Animated.View style={{ opacity: taglineOpacity }}>
        <Text style={styles.tagline}>Football Intelligence Engine</Text>
        <Text style={styles.taglineSub}>Hybrid V1 Algorithm · Claude AI</Text>
      </Animated.View>

      {/* Progress bar */}
      <View style={styles.progressContainer}>
        <Animated.View style={[styles.progressBar, { width: progressWidth }]} />
      </View>

      {/* Version */}
      <Text style={styles.version}>v1.0.0</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#030508',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 40,
  },
  glowTop: {
    position: 'absolute',
    top: -100,
    left: -100,
    width: 400,
    height: 400,
    borderRadius: 200,
    backgroundColor: 'rgba(0, 212, 255, 0.04)',
  },
  glowBottom: {
    position: 'absolute',
    bottom: -100,
    right: -100,
    width: 350,
    height: 350,
    borderRadius: 175,
    backgroundColor: 'rgba(124, 58, 237, 0.05)',
  },
  logoContainer: {
    marginBottom: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shield: {
    width: 100,
    height: 110,
    backgroundColor: '#0055cc',
    borderRadius: 12,
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
    borderBottomLeftRadius: 50,
    borderBottomRightRadius: 50,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: 'rgba(0, 212, 255, 0.4)',
    shadowColor: '#00d4ff',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 20,
    elevation: 12,
  },
  shieldInner: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  shieldLetter: {
    fontSize: 52,
    fontWeight: '900',
    color: '#00d4ff',
    letterSpacing: -2,
    lineHeight: 60,
  },
  appName: {
    fontSize: 32,
    fontWeight: '900',
    letterSpacing: 3,
    marginBottom: 10,
  },
  appNameMatch: {
    color: '#c0e8ff',
  },
  appNameOracle: {
    color: '#00d4ff',
  },
  tagline: {
    fontSize: 13,
    color: '#94a3b8',
    textAlign: 'center',
    letterSpacing: 1,
    marginBottom: 4,
  },
  taglineSub: {
    fontSize: 11,
    color: '#4a6080',
    textAlign: 'center',
    letterSpacing: 0.5,
    marginBottom: 48,
  },
  progressContainer: {
    width: width * 0.6,
    height: 3,
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
    borderRadius: 3,
    overflow: 'hidden',
    marginBottom: 16,
  },
  progressBar: {
    height: '100%',
    backgroundColor: '#00d4ff',
    borderRadius: 3,
    shadowColor: '#00d4ff',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 6,
  },
  version: {
    position: 'absolute',
    bottom: 40,
    fontSize: 11,
    color: '#4a6080',
    letterSpacing: 1,
  },
});
