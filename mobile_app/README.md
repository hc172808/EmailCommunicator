# Email Server Mobile App

A Flutter mobile application for your Email Server with comprehensive email management features.

## Features

- **Secure Authentication** - Login with your email server credentials
- **Email Management** - View, send, and manage emails
- **Real-time Updates** - Pull-to-refresh for latest emails
- **Clean UI** - Modern Material Design interface
- **API Integration** - Direct connection to your email server

## Setup Instructions

### Prerequisites

1. **Flutter SDK** - Install Flutter 3.0 or higher
2. **Android Studio** - For Android development
3. **Xcode** - For iOS development (Mac only)
4. **Your Email Server** - Running with domain configured

### Installation Steps

1. **Extract the ZIP file** to your desired location
2. **Open in your IDE**:
   - Android Studio: File → Open → Select the mobile_app folder
   - VS Code: Open the mobile_app folder

3. **Configure your server URL**:
   - Open `lib/services/api_service.dart`
   - Change the `baseUrl` from `'https://your-domain.com/api'` to your actual server URL

4. **Install dependencies**:
   ```bash
   flutter pub get
   ```

5. **Run the app**:
   ```bash
   flutter run
   ```

### Configuration

#### Server URL Setup
In `lib/services/api_service.dart`, update the base URL:

```dart
static const String baseUrl = 'https://your-actual-domain.com/api';
```

#### Android Configuration
The app includes basic Android configuration. For production:

1. Update `android/app/src/main/AndroidManifest.xml`
2. Configure signing keys for release builds
3. Update app name and package name as needed

#### iOS Configuration
For iOS deployment:

1. Open `ios/Runner.xcworkspace` in Xcode
2. Configure team and bundle identifier
3. Update app name and permissions as needed

### API Endpoints Used

The mobile app connects to these server endpoints:

- `POST /api/auth/login` - User authentication
- `GET /api/emails` - Fetch user emails
- `POST /api/emails/send` - Send new emails

### Troubleshooting

**Connection Issues:**
- Verify your server URL is correct
- Ensure your server has CORS enabled for mobile requests
- Check that the API endpoints are accessible

**Build Issues:**
- Run `flutter doctor` to check your setup
- Ensure all dependencies are properly installed
- Clear build cache with `flutter clean`

**Authentication Issues:**
- Verify your login credentials work on the web interface
- Check server logs for authentication errors

### Development

#### Project Structure
```
lib/
├── main.dart              # App entry point
├── services/              # API and authentication services
├── providers/             # State management
├── screens/              # UI screens
├── models/               # Data models
└── widgets/              # Reusable UI components
```

#### Adding Features
1. Create new screens in `lib/screens/`
2. Add new API services in `lib/services/`
3. Update providers for state management
4. Add navigation routes in `main.dart`

### Deployment

#### Android
1. Build APK: `flutter build apk`
2. Build App Bundle: `flutter build appbundle`
3. Upload to Google Play Store

#### iOS
1. Build for iOS: `flutter build ios`
2. Open in Xcode and archive
3. Upload to App Store Connect

### Support

For issues related to:
- **Mobile App**: Check Flutter documentation
- **Email Server**: Check your server logs and configuration
- **API Connection**: Verify server URL and endpoints

### License

This mobile app is part of your Email Server project and follows the same licensing terms.