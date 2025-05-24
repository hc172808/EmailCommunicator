import 'api_service.dart';

class AuthService {
  final ApiService _apiService;

  AuthService(this._apiService);

  Future<Map<String, dynamic>> login(String username, String password) async {
    return await _apiService.login(username, password);
  }

  Future<void> logout() async {
    await _apiService.clearAuthToken();
  }

  Future<bool> isLoggedIn() async {
    final token = await _apiService.getAuthToken();
    return token != null;
  }
}