import 'package:flutter/material.dart';

class EmailDetailScreen extends StatelessWidget {
  final String emailId;

  EmailDetailScreen({required this.emailId});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Email Details'),
        actions: [
          IconButton(
            icon: Icon(Icons.reply),
            onPressed: () {
              // TODO: Implement reply functionality
            },
          ),
          IconButton(
            icon: Icon(Icons.delete),
            onPressed: () {
              // TODO: Implement delete functionality
            },
          ),
        ],
      ),
      body: Padding(
        padding: EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Email ID: $emailId',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 16),
            Text('Email details will be loaded here...'),
          ],
        ),
      ),
    );
  }
}