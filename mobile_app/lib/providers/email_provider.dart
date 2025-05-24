import 'package:flutter/foundation.dart';
import '../services/api_service.dart';

class EmailProvider with ChangeNotifier {
  final ApiService _apiService;
  
  List<dynamic> _emails = [];
  bool _isLoading = false;
  String? _error;

  EmailProvider(this._apiService);

  List<dynamic> get emails => _emails;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> fetchEmails() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _emails = await _apiService.getEmails();
    } catch (e) {
      _error = e.toString();
    }

    _isLoading = false;
    notifyListeners();
  }

  Future<bool> sendEmail({
    required String recipient,
    required String subject,
    required String body,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _apiService.sendEmail(
        recipient: recipient,
        subject: subject,
        body: body,
      );
      await fetchEmails(); // Refresh emails
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }
}