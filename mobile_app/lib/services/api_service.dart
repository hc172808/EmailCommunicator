import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiService {
  // Change this to your actual server URL
  static const String baseUrl = 'https://your-domain.com/api';
  
  final FlutterSecureStorage _storage = FlutterSecureStorage();
  String? _authToken;

  // Get stored auth token
  Future<String?> getAuthToken() async {
    if (_authToken != null) return _authToken;
    _authToken = await _storage.read(key: 'auth_token');
    return _authToken;
  }

  // Store auth token
  Future<void> setAuthToken(String token) async {
    _authToken = token;
    await _storage.write(key: 'auth_token', value: token);
  }

  // Clear auth token
  Future<void> clearAuthToken() async {
    _authToken = null;
    await _storage.delete(key: 'auth_token');
  }

  // Login user
  Future<Map<String, dynamic>> login(String username, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'username': username,
          'password': password,
        }),
      );

      final data = jsonDecode(response.body);
      
      if (response.statusCode == 200 && data['success'] == true) {
        await setAuthToken(data['token']);
        return data;
      } else {
        throw Exception(data['error'] ?? 'Login failed');
      }
    } catch (e) {
      throw Exception('Network error: $e');
    }
  }

  // Get user emails
  Future<List<dynamic>> getEmails() async {
    try {
      final token = await getAuthToken();
      if (token == null) throw Exception('No auth token');

      final response = await http.get(
        Uri.parse('$baseUrl/emails'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final data = jsonDecode(response.body);
      
      if (response.statusCode == 200 && data['success'] == true) {
        return data['emails'];
      } else {
        throw Exception(data['error'] ?? 'Failed to fetch emails');
      }
    } catch (e) {
      throw Exception('Network error: $e');
    }
  }

  // Send email
  Future<Map<String, dynamic>> sendEmail({
    required String recipient,
    required String subject,
    required String body,
  }) async {
    try {
      final token = await getAuthToken();
      if (token == null) throw Exception('No auth token');

      final response = await http.post(
        Uri.parse('$baseUrl/emails/send'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode({
          'recipient': recipient,
          'subject': subject,
          'body': body,
        }),
      );

      final data = jsonDecode(response.body);
      
      if (response.statusCode == 200 && data['success'] == true) {
        return data;
      } else {
        throw Exception(data['error'] ?? 'Failed to send email');
      }
    } catch (e) {
      throw Exception('Network error: $e');
    }
  }
}